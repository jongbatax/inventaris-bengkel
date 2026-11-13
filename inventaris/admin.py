from django.contrib import admin
from . import models

for m in (models.Bengkel, models.ProgramKeahlian, models.Laboratorium, models.Departemen,
          models.Profile, models.PTK, models.Kategori, models.Barang, models.Pengembalian, models.LogAktivitas):
    admin.site.register(m)


class DetailInline(admin.TabularInline):
    model = models.DetailPeminjaman
    extra = 0


@admin.register(models.Peminjaman)
class PeminjamanAdmin(admin.ModelAdmin):
    inlines = [DetailInline]
    list_display = ("id", "ptk", "laboratorium", "tanggal_pinjam", "tanggal_harus_kembali", "status")
