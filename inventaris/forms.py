from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from .models import Barang, DetailPeminjaman, Peminjaman, PTK


class BarangForm(forms.ModelForm):
    class Meta:
        model = Barang
        fields = ["laboratorium", "kategori", "kode", "nama", "jenis", "kondisi", "satuan", "stok", "keterangan"]
        widgets = {"keterangan": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(user, "profile", None)
        labs = profile.labs() if profile else self.fields["laboratorium"].queryset
        self.fields["laboratorium"].queryset = labs
        if profile and profile.is_laboran:
            self.fields["laboratorium"].initial = profile.laboratorium
            self.fields["laboratorium"].disabled = True
        # Ketersediaan (stok) hanya dikelola Laboran; level lain view-only.
        if profile and not profile.is_laboran:
            self.fields["stok"].disabled = True
            self.fields["stok"].help_text = "Hanya Laboran yang dapat mengubah stok."


class PTKForm(forms.ModelForm):
    class Meta:
        model = PTK
        fields = ["nama", "nip", "departemen", "telepon"]


class PeminjamanForm(forms.ModelForm):
    class Meta:
        model = Peminjaman
        fields = ["ptk", "tanggal_pinjam", "tanggal_harus_kembali", "keperluan"]
        widgets = {
            "tanggal_pinjam": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "tanggal_harus_kembali": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tanggal_pinjam"].initial = timezone.localdate()


class DetailForm(forms.ModelForm):
    class Meta:
        model = DetailPeminjaman
        fields = ["barang", "jumlah"]

    def clean(self):
        data = super().clean()
        b, j = data.get("barang"), data.get("jumlah")
        if b and j:
            if b.is_aset and b.kondisi == Barang.RUSAK_BERAT:
                raise forms.ValidationError(f"{b.nama} rusak berat, tidak dapat dipinjam.")
            if j > b.stok:
                raise forms.ValidationError(f"Stok {b.nama} tidak cukup (tersedia {b.stok}).")
        return data


class BaseDetailFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen, n = set(), 0
        for f in self.forms:
            if not f.cleaned_data or f.cleaned_data.get("DELETE") or not f.cleaned_data.get("barang"):
                continue
            n += 1
            b = f.cleaned_data["barang"]
            if b.pk in seen:
                raise forms.ValidationError(f"{b.nama} dipilih lebih dari sekali.")
            seen.add(b.pk)
        if n == 0:
            raise forms.ValidationError("Pilih minimal satu alat/bahan.")


def detail_formset(lab, **kwargs):
    FS = inlineformset_factory(Peminjaman, DetailPeminjaman, form=DetailForm, formset=BaseDetailFormSet,
                               extra=4, can_delete=False)
    fs = FS(**kwargs)
    qs = Barang.objects.filter(laboratorium=lab, stok__gt=0).select_related("kategori")
    for f in fs.forms:
        f.fields["barang"].queryset = qs
        f.empty_permitted = True
    return fs
