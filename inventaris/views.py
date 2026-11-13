import csv
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .audit import catat, diff_form
from .forms import BarangForm, PeminjamanForm, PTKForm, detail_formset
from .models import (Barang, DetailPeminjaman, Kategori, LogAktivitas, Pengembalian, Peminjaman, PTK)

SOON_DAYS = 3


# ---------- helper akses ----------
def user_labs(user):
    """Laboratorium yang boleh diakses (pembatasan akses per level)."""
    from .models import Laboratorium
    profile = getattr(user, "profile", None)
    if user.is_superuser:
        qs = Laboratorium.objects.all()
    elif profile:
        qs = profile.labs()
    else:
        raise PermissionDenied("Akun belum memiliki profil/level.")
    prog = getattr(user, "program_filter", None)  # diisi middleware (Waka. Sarpras & admin saja)
    return qs.filter(bengkel__program_keahlian=prog) if prog else qs


def is_laboran(user):
    p = getattr(user, "profile", None)
    return bool(p and p.is_laboran)


def laboran_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *a, **kw):
        if not is_laboran(request.user):
            raise PermissionDenied("Hanya Laboran yang dapat melakukan aksi ini.")
        return view(request, *a, **kw)
    return wrapper


def scoped_barang(user):
    return Barang.objects.filter(laboratorium__in=user_labs(user)).select_related("laboratorium", "kategori")


def scoped_peminjaman(user):
    return Peminjaman.objects.filter(laboratorium__in=user_labs(user)).select_related("ptk", "laboratorium")


def scoped_detail(user):
    return DetailPeminjaman.objects.filter(peminjaman__laboratorium__in=user_labs(user)) \
        .select_related("peminjaman__ptk", "peminjaman__laboratorium", "barang")


def unreturned(user):
    """Detail alat (aset) yang belum dikembalikan."""
    return scoped_detail(user).filter(barang__jenis=Barang.ASET, jumlah_kembali__lt=F("jumlah"))


@login_required
def set_program_filter(request):
    from .middleware import can_filter_program
    if can_filter_program(request.user):
        pid = request.GET.get("program", "")
        if pid.isdigit():
            request.session["program_filter"] = int(pid)
        else:
            request.session.pop("program_filter", None)
    return redirect(request.META.get("HTTP_REFERER") or "dashboard")


# ---------- dashboard ----------
@login_required
def dashboard(request):
    u, today = request.user, timezone.localdate()
    barang = scoped_barang(u)
    belum = unreturned(u)
    aktif = scoped_peminjaman(u).filter(status=Peminjaman.DIPINJAM)
    per_bulan = (scoped_peminjaman(u).filter(tanggal_pinjam__gte=today - timedelta(days=180))
                 .annotate(b=TruncMonth("tanggal_pinjam")).values("b").annotate(n=Count("id")).order_by("b"))
    maxn = max([r["n"] for r in per_bulan] or [1])
    ctx = {
        "total_aset": barang.filter(jenis=Barang.ASET).count(),
        "total_habis": barang.filter(jenis=Barang.HABIS_PAKAI).count(),
        "baik": barang.filter(kondisi=Barang.BAIK).count(),
        "rusak_ringan": barang.filter(kondisi=Barang.RUSAK_RINGAN).count(),
        "rusak_berat": barang.filter(kondisi=Barang.RUSAK_BERAT).count(),
        "aktif": aktif.count(),
        "terlambat": aktif.filter(tanggal_harus_kembali__lt=today).count(),
        "stok_menipis": barang.filter(stok__lte=5).order_by("stok")[:8],
        "jatuh_tempo": belum.filter(peminjaman__tanggal_harus_kembali__lte=today + timedelta(days=SOON_DAYS))
                            .order_by("peminjaman__tanggal_harus_kembali")[:8],
        "top_barang": DetailPeminjaman.objects.filter(peminjaman__in=scoped_peminjaman(u))
                          .values("barang__nama").annotate(total=Sum("jumlah")).order_by("-total")[:5],
        "per_bulan": [{"label": r["b"].strftime("%b %Y"), "n": r["n"], "pct": int(r["n"] / maxn * 100)}
                      for r in per_bulan],
        "today": today,
    }
    return render(request, "inventaris/dashboard.html", ctx)


# ---------- barang ----------
@login_required
def barang_list(request):
    qs = scoped_barang(request.user)
    q, jenis, kondisi = request.GET.get("q", ""), request.GET.get("jenis", ""), request.GET.get("kondisi", "")
    if q:
        qs = qs.filter(Q(nama__icontains=q) | Q(kode__icontains=q))
    if jenis:
        qs = qs.filter(jenis=jenis)
    if kondisi:
        qs = qs.filter(kondisi=kondisi)
    return render(request, "inventaris/barang_list.html", {
        "items": qs, "q": q, "jenis": jenis, "kondisi": kondisi,
        "JENIS": Barang.JENIS_CHOICES, "KONDISI": Barang.KONDISI_CHOICES})


@login_required
def barang_form(request, pk=None):
    obj = get_object_or_404(scoped_barang(request.user), pk=pk) if pk else None
    form = BarangForm(request.POST or None, instance=obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        b = form.save(commit=False)
        if is_laboran(request.user):
            b.laboratorium = request.user.profile.laboratorium
        detail = diff_form(form) if obj else f"Stok awal {b.stok} {b.satuan}; status {b.get_kondisi_display()}"
        if not obj:
            b.dibuat_oleh = request.user
        b.diubah_oleh = request.user
        b.save()
        if not obj or detail:
            catat(request.user, "ubah" if obj else "tambah", "Barang", b, b.laboratorium, detail)
        messages.success(request, "Data barang disimpan.")
        return redirect("barang_list")
    return render(request, "inventaris/form.html", {"form": form, "title": "Ubah Barang" if obj else "Tambah Barang",
                                                    "back": "barang_list"})


@login_required
def barang_delete(request, pk):
    obj = get_object_or_404(scoped_barang(request.user), pk=pk)
    if request.method == "POST":
        try:
            nama, lab = str(obj), obj.laboratorium
            obj.delete()
            catat(request.user, "hapus", "Barang", nama, lab)
            messages.success(request, "Barang dihapus.")
        except Exception:
            messages.error(request, "Barang tidak dapat dihapus karena sudah punya riwayat peminjaman.")
        return redirect("barang_list")
    return render(request, "inventaris/confirm_delete.html", {"obj": obj, "back": "barang_list"})


# ---------- PTK ----------
@login_required
def ptk_list(request):
    q = request.GET.get("q", "")
    qs = PTK.objects.select_related("departemen")
    if q:
        qs = qs.filter(Q(nama__icontains=q) | Q(nip__icontains=q) | Q(departemen__nama__icontains=q))
    return render(request, "inventaris/ptk_list.html", {"items": qs, "q": q})


@laboran_required
def ptk_form(request, pk=None):
    obj = get_object_or_404(PTK, pk=pk) if pk else None
    form = PTKForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        detail = diff_form(form) if obj else ""
        saved = form.save()
        if not obj or detail:
            catat(request.user, "ubah" if obj else "tambah", "PTK", saved, request.user.profile.laboratorium, detail)
        messages.success(request, "Data PTK disimpan.")
        return redirect("ptk_list")
    return render(request, "inventaris/form.html", {"form": form, "title": "Ubah PTK" if obj else "Tambah PTK",
                                                    "back": "ptk_list"})


@laboran_required
def ptk_delete(request, pk):
    obj = get_object_or_404(PTK, pk=pk)
    if request.method == "POST":
        try:
            nama = str(obj)
            obj.delete()
            catat(request.user, "hapus", "PTK", nama, request.user.profile.laboratorium)
            messages.success(request, "PTK dihapus.")
        except Exception:
            messages.error(request, "PTK tidak dapat dihapus karena sudah punya riwayat peminjaman.")
        return redirect("ptk_list")
    return render(request, "inventaris/confirm_delete.html", {"obj": obj, "back": "ptk_list"})


# ---------- peminjaman ----------
@login_required
def peminjaman_list(request):
    qs = scoped_peminjaman(request.user)
    status = request.GET.get("status", "")
    if status in (Peminjaman.DIPINJAM, Peminjaman.SELESAI):
        qs = qs.filter(status=status)
    return render(request, "inventaris/peminjaman_list.html", {"items": qs, "status": status})


@login_required
def peminjaman_detail(request, pk):
    p = get_object_or_404(scoped_peminjaman(request.user), pk=pk)
    return render(request, "inventaris/peminjaman_detail.html", {
        "p": p, "details": p.detail.select_related("barang").prefetch_related("pengembalian")})


@laboran_required
def peminjaman_create(request):
    lab = request.user.profile.laboratorium
    form = PeminjamanForm(request.POST or None)
    fs = detail_formset(lab, data=request.POST or None, instance=Peminjaman())
    if request.method == "POST" and form.is_valid() and fs.is_valid():
        with transaction.atomic():
            p = form.save(commit=False)
            p.laboratorium, p.dibuat_oleh = lab, request.user
            p.save()
            for f in fs.forms:
                cd = f.cleaned_data
                if not cd or not cd.get("barang"):
                    continue
                b = Barang.objects.select_for_update().get(pk=cd["barang"].pk)
                if cd["jumlah"] > b.stok:
                    transaction.set_rollback(True)
                    messages.error(request, f"Stok {b.nama} berubah, tidak cukup.")
                    return redirect("peminjaman_create")
                DetailPeminjaman.objects.create(peminjaman=p, barang=b, jumlah=cd["jumlah"])
                b.stok -= cd["jumlah"]  # aset: tidak tersedia selama dipinjam; habis pakai: berkurang permanen
                b.save(update_fields=["stok"])
            p.refresh_status()
            ringkas = ", ".join(f"{d.barang.nama} x{d.jumlah}" for d in p.detail.select_related("barang"))
            catat(request.user, "tambah", "Peminjaman", f"{p.kode} / {p.ptk}", lab, ringkas)
        messages.success(request, f"{p.kode} tersimpan.")
        return redirect("peminjaman_detail", pk=p.pk)
    return render(request, "inventaris/peminjaman_form.html", {"form": form, "fs": fs, "lab": lab})


# ---------- pengembalian ----------
@login_required
def pengembalian_list(request):
    today = timezone.localdate()
    belum = unreturned(request.user).order_by("peminjaman__tanggal_harus_kembali")
    soon = belum.filter(peminjaman__tanggal_harus_kembali__gte=today,
                        peminjaman__tanggal_harus_kembali__lte=today + timedelta(days=SOON_DAYS))
    riwayat = Pengembalian.objects.filter(detail__peminjaman__laboratorium__in=user_labs(request.user)) \
        .select_related("detail__barang", "detail__peminjaman__ptk")[:20]
    return render(request, "inventaris/pengembalian_list.html", {
        "belum": belum, "soon": soon, "riwayat": riwayat, "today": today, "soon_days": SOON_DAYS})


@laboran_required
def pengembalian_form(request, pk):
    p = get_object_or_404(scoped_peminjaman(request.user), pk=pk)
    rows = [d for d in p.detail.select_related("barang") if d.sisa > 0]
    if not rows:
        messages.info(request, "Semua alat pada peminjaman ini sudah dikembalikan.")
        return redirect("peminjaman_detail", pk=p.pk)
    if request.method == "POST":
        tanggal = request.POST.get("tanggal") or timezone.localdate()
        errors, todo = [], []
        for d in rows:
            try:
                jml = int(request.POST.get(f"jml_{d.id}") or 0)
            except ValueError:
                jml = -1
            kond = request.POST.get(f"kondisi_{d.id}", Barang.BAIK)
            if jml < 0 or jml > d.sisa or kond not in dict(Barang.KONDISI_CHOICES):
                errors.append(f"{d.barang.nama}: jumlah harus 0-{d.sisa}.")
            elif jml > 0:
                todo.append((d, jml, kond))
        if not todo and not errors:
            errors.append("Isi jumlah yang dikembalikan minimal satu alat.")
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            with transaction.atomic():
                for d, jml, kond in todo:
                    Pengembalian.objects.create(detail=d, tanggal=tanggal, jumlah=jml, kondisi=kond,
                                                catatan=request.POST.get(f"catatan_{d.id}", ""),
                                                diterima_oleh=request.user)
                    d.jumlah_kembali += jml
                    d.save(update_fields=["jumlah_kembali"])
                    b = d.barang
                    b.stok += jml
                    # MVP: kondisi barang mengikuti kondisi terburuk yang dilaporkan saat kembali
                    if Barang.KONDISI_RANK[kond] > Barang.KONDISI_RANK[b.kondisi]:
                        b.kondisi = kond
                    b.save(update_fields=["stok", "kondisi"])
                p.refresh_status()
                ringkas = ", ".join(f"{d.barang.nama} x{j} ({dict(Barang.KONDISI_CHOICES)[k]})" for d, j, k in todo)
                catat(request.user, "tambah", "Pengembalian", f"{p.kode} / {p.ptk}", p.laboratorium, ringkas)
            messages.success(request, "Pengembalian dicatat.")
            return redirect("peminjaman_detail", pk=p.pk)
    return render(request, "inventaris/pengembalian_form.html", {
        "p": p, "rows": rows, "KONDISI": Barang.KONDISI_CHOICES, "today": timezone.localdate()})


# ---------- riwayat ----------
@login_required
def riwayat(request):
    ptk_id, barang_id = request.GET.get("ptk", ""), request.GET.get("barang", "")
    qs = scoped_detail(request.user).order_by("-peminjaman__tanggal_pinjam", "-id")
    if ptk_id:
        qs = qs.filter(peminjaman__ptk_id=ptk_id)
    if barang_id:
        qs = qs.filter(barang_id=barang_id)
    return render(request, "inventaris/riwayat.html", {
        "items": qs, "ptk_list": PTK.objects.all(), "barang_list": scoped_barang(request.user),
        "ptk_id": ptk_id, "barang_id": barang_id})


# ---------- laporan ----------
LAPORAN = {
    "barang": "Laporan Alat/Bahan",
    "peminjaman": "Laporan Peminjaman & Pengembalian",
    "stok": "Laporan Stok Alat/Bahan",
    "belum-kembali": "Rekapitulasi Alat Belum Dikembalikan",
}


@login_required
def laporan(request, jenis):
    if jenis not in LAPORAN:
        raise PermissionDenied
    u, g = request.user, request.GET
    kondisi, jns = g.get("kondisi", ""), g.get("jenis", "")
    dari, sampai = g.get("dari", ""), g.get("sampai", "")
    if jenis in ("barang", "stok"):
        qs = scoped_barang(u)
        if kondisi:
            qs = qs.filter(kondisi=kondisi)
        if jns:
            qs = qs.filter(jenis=jns)
        if jenis == "barang":
            head = ["Kode", "Nama", "Kategori", "Jenis", "Status", "Laboratorium"]
            rows = [[b.kode, b.nama, b.kategori, b.get_jenis_display(), b.get_kondisi_display(), b.laboratorium]
                    for b in qs]
        else:
            head = ["Kode", "Nama", "Jenis", "Status", "Stok Tersedia", "Sedang Dipinjam", "Satuan", "Laboratorium"]
            rows = [[b.kode, b.nama, b.get_jenis_display(), b.get_kondisi_display(), b.stok, b.dipinjam,
                     b.satuan, b.laboratorium] for b in qs.prefetch_related("detail_peminjaman__barang")]
    elif jenis == "peminjaman":
        qs = scoped_detail(u).prefetch_related("pengembalian").order_by("-peminjaman__tanggal_pinjam")
        if dari:
            qs = qs.filter(peminjaman__tanggal_pinjam__gte=dari)
        if sampai:
            qs = qs.filter(peminjaman__tanggal_pinjam__lte=sampai)
        head = ["Kode", "PTK", "Barang", "Jumlah", "Tgl Pinjam", "Harus Kembali", "Tgl Kembali", "Dikembalikan", "Lab"]
        rows = []
        for d in qs:
            last = d.pengembalian.all()[0].tanggal if d.pengembalian.all() else "-"
            rows.append([d.peminjaman.kode, d.peminjaman.ptk, d.barang.nama, d.jumlah, d.peminjaman.tanggal_pinjam,
                         d.peminjaman.tanggal_harus_kembali, last,
                         d.jumlah_kembali if d.barang.is_aset else "habis pakai", d.peminjaman.laboratorium])
    else:
        today = timezone.localdate()
        qs = unreturned(u).order_by("peminjaman__tanggal_harus_kembali")
        head = ["Kode", "PTK", "Departemen", "Barang", "Belum Kembali", "Harus Kembali", "Keterlambatan (hari)", "Lab"]
        rows = [[d.peminjaman.kode, d.peminjaman.ptk, d.peminjaman.ptk.departemen, d.barang.nama, d.sisa,
                 d.peminjaman.tanggal_harus_kembali,
                 max((today - d.peminjaman.tanggal_harus_kembali).days, 0), d.peminjaman.laboratorium]
                for d in qs.select_related("peminjaman__ptk__departemen")]
    if g.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="laporan-{jenis}.csv"'
        w = csv.writer(resp)
        w.writerow(head)
        w.writerows([[str(c) for c in r] for r in rows])
        return resp
    return render(request, "inventaris/laporan.html", {
        "jenis": jenis, "judul": LAPORAN[jenis], "head": head, "rows": rows, "kondisi": kondisi, "jns": jns,
        "dari": dari, "sampai": sampai, "KONDISI": Barang.KONDISI_CHOICES, "JENIS": Barang.JENIS_CHOICES,
        "today": timezone.localdate()})


# ---------- log aktivitas ----------
@login_required
def log_aktivitas(request):
    from django.contrib.auth.models import User
    labs = user_labs(request.user)
    qs = LogAktivitas.objects.filter(laboratorium__in=labs).select_related("user", "laboratorium")
    g = request.GET
    objek, aksi, uid = g.get("objek", ""), g.get("aksi", ""), g.get("user", "")
    if objek:
        qs = qs.filter(objek=objek)
    if aksi:
        qs = qs.filter(aksi=aksi)
    if uid:
        qs = qs.filter(user_id=uid)
    users = User.objects.filter(pk__in=LogAktivitas.objects.filter(laboratorium__in=labs).values("user"))
    return render(request, "inventaris/log.html", {
        "items": qs[:300], "users": users, "objek": objek, "aksi": aksi, "uid": uid,
        "OBJEK": ["Barang", "PTK", "Peminjaman", "Pengembalian"], "AKSI": LogAktivitas.AKSI_CHOICES})
