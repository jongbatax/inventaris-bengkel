from .models import LogAktivitas


def catat(user, aksi, objek, nama, lab=None, detail=""):
    LogAktivitas.objects.create(user=user, aksi=aksi, objek=objek, objek_nama=str(nama)[:200],
                                laboratorium=lab, detail=detail)


def diff_form(form):
    """Ringkasan perubahan field: 'Status: Baik -> Rusak Berat'."""
    out = []
    for name in form.changed_data:
        f = form.fields[name]
        old, new = form.initial.get(name), form.cleaned_data.get(name)
        if hasattr(f, "queryset") and old is not None:
            old = f.queryset.model.objects.filter(pk=old).first()
        if not hasattr(f, "queryset"):
            choices = dict(getattr(f, "choices", []) or [])
            old, new = choices.get(old, old), choices.get(new, new)
        out.append(f"{f.label or name}: {old if old not in (None, '') else '-'} -> {new if new not in (None, '') else '-'}")
    return "; ".join(out)
