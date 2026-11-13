from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ProgramKeahlian(models.Model):
    """Level tertinggi: membawahi beberapa bengkel (mis. Otomotif -> TKR, TSM)."""
    nama = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Program Keahlian"
        verbose_name_plural = "Program Keahlian"

    def __str__(self):
        return self.nama


class Bengkel(models.Model):
    nama = models.CharField(max_length=100, unique=True)
    program_keahlian = models.ForeignKey(ProgramKeahlian, on_delete=models.PROTECT, related_name="bengkel")

    class Meta:
        verbose_name_plural = "Bengkel"

    def __str__(self):
        return self.nama


class Laboratorium(models.Model):
    nama = models.CharField(max_length=100)
    bengkel = models.ForeignKey(Bengkel, on_delete=models.PROTECT, related_name="laboratorium")

    class Meta:
        verbose_name_plural = "Laboratorium"
        unique_together = ("nama", "bengkel")

    def __str__(self):
        return self.nama


class Departemen(models.Model):
    """Asal departemen PTK."""
    nama = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Departemen"

    def __str__(self):
        return self.nama


class Profile(models.Model):
    """Level pengguna + cakupan akses (pembatasan akses)."""
    LABORAN, KABENGKEL, KAPROGRAM, WAKASARPRAS = "laboran", "kabengkel", "kaprogram", "wakasarpras"
    ROLE_CHOICES = [
        (LABORAN, "Laboran (PLP)"),
        (KABENGKEL, "Ka. Bengkel"),
        (KAPROGRAM, "Ka. Program"),
        (WAKASARPRAS, "Waka. Sarpras"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    laboratorium = models.ForeignKey(Laboratorium, null=True, blank=True, on_delete=models.PROTECT,
                                     help_text="Wajib untuk Laboran")
    bengkel = models.ForeignKey(Bengkel, null=True, blank=True, on_delete=models.PROTECT,
                                help_text="Wajib untuk Ka. Bengkel")
    program_keahlian = models.ForeignKey(ProgramKeahlian, null=True, blank=True, on_delete=models.PROTECT,
                                         help_text="Wajib untuk Ka. Program")

    def clean(self):
        need = {self.LABORAN: "laboratorium", self.KABENGKEL: "bengkel", self.KAPROGRAM: "program_keahlian"}
        f = need.get(self.role)
        if f and not getattr(self, f):
            raise ValidationError({f: "Wajib diisi untuk level ini."})

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_laboran(self):
        return self.role == self.LABORAN

    def labs(self):
        """Laboratorium yang boleh dilihat user ini."""
        qs = Laboratorium.objects.all()
        if self.role == self.LABORAN:
            return qs.filter(pk=self.laboratorium_id)
        if self.role == self.KABENGKEL:
            return qs.filter(bengkel_id=self.bengkel_id)
        if self.role == self.KAPROGRAM:
            return qs.filter(bengkel__program_keahlian_id=self.program_keahlian_id)
        return qs  # Waka Sarpras: tanpa pembatasan


class PTK(models.Model):
    """Pendidik & Tenaga Kependidikan (peminjam)."""
    nama = models.CharField(max_length=150)
    nip = models.CharField("NIP/NUPTK", max_length=30, unique=True)
    departemen = models.ForeignKey(Departemen, on_delete=models.PROTECT, related_name="ptk")
    telepon = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "PTK"
        verbose_name_plural = "PTK"
        ordering = ["nama"]

    def __str__(self):
        return self.nama


class Kategori(models.Model):
    nama = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Kategori"

    def __str__(self):
        return self.nama


class Barang(models.Model):
    ASET, HABIS_PAKAI = "aset", "habis_pakai"
    JENIS_CHOICES = [(ASET, "Alat (Aset)"), (HABIS_PAKAI, "Barang Habis Pakai")]
    BAIK, RUSAK_RINGAN, RUSAK_BERAT = "baik", "rusak_ringan", "rusak_berat"
    KONDISI_CHOICES = [(BAIK, "Baik"), (RUSAK_RINGAN, "Rusak Ringan"), (RUSAK_BERAT, "Rusak Berat")]
    KONDISI_RANK = {BAIK: 0, RUSAK_RINGAN: 1, RUSAK_BERAT: 2}

    laboratorium = models.ForeignKey(Laboratorium, on_delete=models.PROTECT, related_name="barang")
    kategori = models.ForeignKey(Kategori, on_delete=models.PROTECT, related_name="barang")
    kode = models.CharField(max_length=30)
    nama = models.CharField(max_length=150)
    jenis = models.CharField(max_length=15, choices=JENIS_CHOICES, default=ASET)
    kondisi = models.CharField("Status barang", max_length=15, choices=KONDISI_CHOICES, default=BAIK)
    satuan = models.CharField(max_length=20, default="unit")
    stok = models.PositiveIntegerField("Stok tersedia", default=0)
    keterangan = models.TextField(blank=True)
    dibuat_oleh = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    diubah_oleh = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    diubah_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Barang"
        unique_together = ("laboratorium", "kode")
        ordering = ["nama"]

    def __str__(self):
        return f"{self.kode} - {self.nama}"

    @property
    def is_aset(self):
        return self.jenis == self.ASET

    @property
    def dipinjam(self):
        """Jumlah alat (aset) yang sedang dipinjam."""
        if not self.is_aset:
            return 0
        return sum(d.sisa for d in self.detail_peminjaman.all())

    @property
    def dapat_dipinjam(self):
        return self.stok > 0 and not (self.is_aset and self.kondisi == self.RUSAK_BERAT)


class Peminjaman(models.Model):
    DIPINJAM, SELESAI = "dipinjam", "selesai"
    STATUS_CHOICES = [(DIPINJAM, "Masih Dipinjam"), (SELESAI, "Selesai")]

    ptk = models.ForeignKey(PTK, on_delete=models.PROTECT, related_name="peminjaman")
    laboratorium = models.ForeignKey(Laboratorium, on_delete=models.PROTECT, related_name="peminjaman")
    tanggal_pinjam = models.DateField("Tanggal peminjaman/permintaan", default=timezone.localdate)
    tanggal_harus_kembali = models.DateField("Tanggal harus dikembalikan")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DIPINJAM)
    keperluan = models.CharField(max_length=200, blank=True)
    dibuat_oleh = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Peminjaman"
        ordering = ["-tanggal_pinjam", "-id"]

    def __str__(self):
        return f"PJM-{self.pk:05d} / {self.ptk}"

    def clean(self):
        if self.tanggal_pinjam and self.tanggal_harus_kembali and self.tanggal_harus_kembali < self.tanggal_pinjam:
            raise ValidationError({"tanggal_harus_kembali": "Tidak boleh sebelum tanggal peminjaman."})

    @property
    def kode(self):
        return f"PJM-{self.pk:05d}"

    @property
    def terlambat(self):
        return self.status == self.DIPINJAM and self.tanggal_harus_kembali < timezone.localdate()

    def refresh_status(self):
        belum = any(d.sisa > 0 for d in self.detail.select_related("barang"))
        self.status = self.DIPINJAM if belum else self.SELESAI
        self.save(update_fields=["status"])


class DetailPeminjaman(models.Model):
    peminjaman = models.ForeignKey(Peminjaman, on_delete=models.CASCADE, related_name="detail")
    barang = models.ForeignKey(Barang, on_delete=models.PROTECT, related_name="detail_peminjaman")
    jumlah = models.PositiveIntegerField(default=1)
    jumlah_kembali = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.barang.nama} x{self.jumlah}"

    @property
    def sisa(self):
        """Yang belum dikembalikan; barang habis pakai tidak dikembalikan."""
        return max(self.jumlah - self.jumlah_kembali, 0) if self.barang.is_aset else 0


class Pengembalian(models.Model):
    detail = models.ForeignKey(DetailPeminjaman, on_delete=models.CASCADE, related_name="pengembalian")
    tanggal = models.DateField(default=timezone.localdate)
    jumlah = models.PositiveIntegerField()
    kondisi = models.CharField("Kondisi saat kembali", max_length=15, choices=Barang.KONDISI_CHOICES,
                               default=Barang.BAIK)
    catatan = models.CharField(max_length=200, blank=True)
    diterima_oleh = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name_plural = "Pengembalian"
        ordering = ["-tanggal", "-id"]

    def __str__(self):
        return f"Kembali {self.detail} ({self.tanggal})"


class LogAktivitas(models.Model):
    """Audit trail: siapa melakukan apa, kapan."""
    TAMBAH, UBAH, HAPUS = "tambah", "ubah", "hapus"
    AKSI_CHOICES = [(TAMBAH, "Tambah"), (UBAH, "Ubah"), (HAPUS, "Hapus")]

    waktu = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    aksi = models.CharField(max_length=10, choices=AKSI_CHOICES)
    objek = models.CharField("Objek", max_length=30)      # Barang / PTK / Peminjaman / Pengembalian
    objek_nama = models.CharField(max_length=200)
    laboratorium = models.ForeignKey(Laboratorium, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    detail = models.TextField(blank=True)

    class Meta:
        verbose_name = "Log Aktivitas"
        verbose_name_plural = "Log Aktivitas"
        ordering = ["-waktu", "-id"]

    def __str__(self):
        return f"{self.waktu:%Y-%m-%d %H:%M} {self.user} {self.aksi} {self.objek} {self.objek_nama}"
