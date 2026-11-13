from django.urls import path
from . import views as v

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("filter-jurusan/", v.set_program_filter, name="set_program"),
    path("barang/", v.barang_list, name="barang_list"),
    path("barang/tambah/", v.barang_form, name="barang_create"),
    path("barang/<int:pk>/ubah/", v.barang_form, name="barang_edit"),
    path("barang/<int:pk>/hapus/", v.barang_delete, name="barang_delete"),
    path("ptk/", v.ptk_list, name="ptk_list"),
    path("ptk/tambah/", v.ptk_form, name="ptk_create"),
    path("ptk/<int:pk>/ubah/", v.ptk_form, name="ptk_edit"),
    path("ptk/<int:pk>/hapus/", v.ptk_delete, name="ptk_delete"),
    path("peminjaman/", v.peminjaman_list, name="peminjaman_list"),
    path("peminjaman/baru/", v.peminjaman_create, name="peminjaman_create"),
    path("peminjaman/<int:pk>/", v.peminjaman_detail, name="peminjaman_detail"),
    path("peminjaman/<int:pk>/kembali/", v.pengembalian_form, name="pengembalian_form"),
    path("pengembalian/", v.pengembalian_list, name="pengembalian_list"),
    path("riwayat/", v.riwayat, name="riwayat"),
    path("log/", v.log_aktivitas, name="log"),
    path("laporan/<str:jenis>/", v.laporan, name="laporan"),
]
