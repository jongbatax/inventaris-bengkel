# SI Peminjaman Alat Bengkel (MVP Demo)

    pip install -r requirements.txt
    python manage.py makemigrations inventaris
    python manage.py migrate
    python manage.py seed_demo
    python manage.py runserver

Login: password semua akun demo `demo12345`

Hierarki: Program Keahlian -> Bengkel -> Laboratorium.

| Username | Level | Cakupan |
|---|---|---|
| laboran_jaringan / laboran_komputer / laboran_tkr / laboran_tsm | Laboran | 1 laboratorium |
| kabengkel_tkj, kabengkel_tkr | Ka. Bengkel | hanya lab di bengkelnya |
| kaprogram_ti | Ka. Program | lab di Bengkel TKJ + RPL |
| kaprogram_otomotif | Ka. Program | lab di Bengkel TKR + TSM |
| wakasarpras | Waka. Sarpras | semua lab |
| admin | Superuser (/admin/) | master data |

Jika sebelumnya sudah menjalankan versi lama: hapus `db.sqlite3` dan folder `inventaris/migrations/0*.py`, lalu ulangi langkah di atas.
