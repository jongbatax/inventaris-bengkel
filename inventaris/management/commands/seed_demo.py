from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventaris.models import (Barang, Bengkel, Departemen, DetailPeminjaman, Kategori, Laboratorium, Pengembalian,
                               Peminjaman, Profile, ProgramKeahlian, PTK)

PASSWORD = "demo12345"


class Command(BaseCommand):
    help = "Isi data demo + akun pengguna per level."

    @transaction.atomic
    def handle(self, *a, **kw):
        today = timezone.localdate()
        ti = ProgramKeahlian.objects.get_or_create(nama="Teknologi Informasi")[0]
        oto = ProgramKeahlian.objects.get_or_create(nama="Teknik Otomotif")[0]
        tkj = Bengkel.objects.get_or_create(nama="Bengkel TKJ", program_keahlian=ti)[0]
        rpl = Bengkel.objects.get_or_create(nama="Bengkel RPL", program_keahlian=ti)[0]
        tkr = Bengkel.objects.get_or_create(nama="Bengkel TKR", program_keahlian=oto)[0]
        tsm = Bengkel.objects.get_or_create(nama="Bengkel TSM", program_keahlian=oto)[0]
        jar = Laboratorium.objects.get_or_create(nama="Lab Jaringan", bengkel=tkj)[0]
        kom = Laboratorium.objects.get_or_create(nama="Lab Komputer", bengkel=rpl)[0]
        eng = Laboratorium.objects.get_or_create(nama="Lab Engine", bengkel=tkr)[0]
        mot = Laboratorium.objects.get_or_create(nama="Lab Sepeda Motor", bengkel=tsm)[0]

        users = [  # username, nama, role, lab/bengkel/program
            ("laboran_jaringan", "Budi (Laboran Jaringan)", "laboran", dict(laboratorium=jar)),
            ("laboran_komputer", "Sari (Laboran Komputer)", "laboran", dict(laboratorium=kom)),
            ("laboran_tkr", "Joko (Laboran Engine TKR)", "laboran", dict(laboratorium=eng)),
            ("laboran_tsm", "Agus (Laboran Sepeda Motor)", "laboran", dict(laboratorium=mot)),
            ("kabengkel_tkj", "Ka. Bengkel TKJ", "kabengkel", dict(bengkel=tkj)),
            ("kabengkel_tkr", "Ka. Bengkel TKR", "kabengkel", dict(bengkel=tkr)),
            ("kaprogram_ti", "Ka. Program Teknologi Informasi", "kaprogram", dict(program_keahlian=ti)),
            ("kaprogram_otomotif", "Ka. Program Otomotif", "kaprogram", dict(program_keahlian=oto)),
            ("wakasarpras", "Waka. Sarpras", "wakasarpras", {}),
        ]
        for uname, nama, role, scope in users:
            u, _ = User.objects.get_or_create(username=uname, defaults={"first_name": nama})
            u.set_password(PASSWORD)
            u.save()
            Profile.objects.update_or_create(user=u, defaults={"role": role, **scope})
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", password=PASSWORD)

        dept = {n: Departemen.objects.get_or_create(nama=n)[0]
                for n in ["Teknik Komputer & Jaringan", "Rekayasa Perangkat Lunak", "Otomotif", "Umum/Tata Usaha"]}
        ptk = [PTK.objects.get_or_create(nip=nip, defaults=dict(nama=n, departemen=dept[d]))[0] for n, nip, d in [
            ("Andi Pratama, S.Kom", "198801012015", "Teknik Komputer & Jaringan"),
            ("Rina Wulandari, S.Pd", "199002022016", "Rekayasa Perangkat Lunak"),
            ("Dedi Kurniawan, S.T", "198503032014", "Otomotif"),
            ("Maya Sari, S.Pd", "199204042018", "Umum/Tata Usaha")]]

        kat = {n: Kategori.objects.get_or_create(nama=n)[0] for n in ["Alat Ukur", "Perkakas", "Perangkat Komputer", "Kabel & Konektor"]}
        A, H = Barang.ASET, Barang.HABIS_PAKAI
        data = [  # lab, kode, nama, kat, jenis, kondisi, satuan, stok
            (jar, "JAR-001", "Multimeter Digital", "Alat Ukur", A, "baik", "unit", 6),
            (jar, "JAR-002", "Tang Crimping RJ45", "Perkakas", A, "baik", "unit", 8),
            (jar, "JAR-003", "LAN Tester", "Alat Ukur", A, "rusak_ringan", "unit", 3),
            (jar, "JAR-004", "Kabel UTP Cat6", "Kabel & Konektor", H, "baik", "meter", 120),
            (jar, "JAR-005", "Konektor RJ45", "Kabel & Konektor", H, "baik", "pcs", 4),
            (jar, "JAR-006", "Crimping Tool Lama", "Perkakas", A, "rusak_berat", "unit", 1),
            (kom, "KOM-001", "Laptop Praktik", "Perangkat Komputer", A, "baik", "unit", 10),
            (kom, "KOM-002", "Proyektor", "Perangkat Komputer", A, "baik", "unit", 2),
            (kom, "KOM-003", "Flashdisk 32GB", "Perangkat Komputer", H, "baik", "pcs", 15),
            (eng, "ENG-001", "Kunci Pas Set", "Perkakas", A, "baik", "set", 5),
            (eng, "ENG-002", "Oli Mesin", "Perkakas", H, "baik", "liter", 20),
            (mot, "MOT-001", "Kunci Busi", "Perkakas", A, "baik", "unit", 6),
        ]
        brg = {}
        for lab, kode, nama, k, j, kond, sat, stok in data:
            brg[kode] = Barang.objects.get_or_create(laboratorium=lab, kode=kode, defaults=dict(
                nama=nama, kategori=kat[k], jenis=j, kondisi=kond, satuan=sat, stok=stok))[0]

        if not Peminjaman.objects.exists():
            admin_user = User.objects.get(username="laboran_jaringan")
            kom_user = User.objects.get(username="laboran_komputer")

            def pinjam(lab, who, user, pinjam_d, kembali_d, items, kembalikan=False):
                p = Peminjaman.objects.create(ptk=who, laboratorium=lab, tanggal_pinjam=pinjam_d,
                                              tanggal_harus_kembali=kembali_d, dibuat_oleh=user,
                                              keperluan="Praktik / kegiatan belajar")
                for kode, n in items:
                    b = brg[kode]
                    d = DetailPeminjaman.objects.create(peminjaman=p, barang=b, jumlah=n)
                    b.stok -= n
                    b.save(update_fields=["stok"])
                    if kembalikan and b.is_aset:
                        Pengembalian.objects.create(detail=d, tanggal=kembali_d, jumlah=n, diterima_oleh=user)
                        d.jumlah_kembali = n
                        d.save(update_fields=["jumlah_kembali"])
                        b.stok += n
                        b.save(update_fields=["stok"])
                p.refresh_status()

            pinjam(jar, ptk[0], admin_user, today - timedelta(days=10), today - timedelta(days=5), [("JAR-001", 2), ("JAR-004", 10)])  # terlambat
            pinjam(jar, ptk[1], admin_user, today - timedelta(days=2), today + timedelta(days=2), [("JAR-002", 3)])  # segera jatuh tempo
            pinjam(jar, ptk[3], admin_user, today - timedelta(days=20), today - timedelta(days=15), [("JAR-001", 1)], kembalikan=True)
            pinjam(kom, ptk[1], kom_user, today - timedelta(days=1), today + timedelta(days=6), [("KOM-001", 2), ("KOM-003", 3)])
        self.stdout.write(self.style.SUCCESS(f"Seed selesai. Password semua akun demo: {PASSWORD}"))
