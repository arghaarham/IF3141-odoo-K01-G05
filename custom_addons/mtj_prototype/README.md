# Toko Maju Jaya — Prototipe IF3141 K01 G05

Add-on `mtj_prototype` menyediakan login dan akses (F-01), produk dan pemetaan satuan (F-02), serta akun dan penugasan peran (F-16). Lingkungan uji memakai Odoo Community 17, PostgreSQL 16, dan Docker Compose. Add-on berlisensi LGPL-3 dan bergantung pada `base`, `web`, serta `uom`.

## Instalasi dan akun uji

Siapkan `.env` dan Docker mengikuti [panduan repo](../../README.md#quick-start). Jalankan perintah berikut dari akar repo. Ganti `odoo_app` dengan `ODOO_DB_NAME` jika berbeda.

```sh
docker compose up -d db
docker compose run --rm web odoo -d odoo_app -i mtj_prototype --stop-after-init --without-demo=all
docker compose up -d web
```

Buka `http://localhost:8069` atau port `ODOO_PORT`. Masuk sebagai admin awal Odoo, buka aplikasi **Toko Maju Jaya → Akun dan Penugasan**, lalu pilih `mtj.admin.uji` dan gunakan **Atur Kata Sandi**. Setelah itu masuk sebagai `mtj.admin.uji` untuk menyiapkan kata sandi akun lain dan menjalankan demo A-06. Semua akun uji awal dimuat tanpa kata sandi yang dapat dipakai untuk masuk. Simpan akses lingkungan uji secara lokal dan gunakan profil atau jendela privat baru saat berpindah akun.

| Nama login | Peran | Lingkup | ID grup relatif terhadap `mtj_prototype` |
|---|---|---|---|
| `mtj.pencatat` | A-01 Pencatat Pesanan | Pesanan | `group_mtj_order_recorder` |
| `mtj.pembayaran` | A-02 Pemeriksa Pembayaran | Pesanan | `group_mtj_payment_reviewer` |
| `mtj.pemenuhan` | A-03 Petugas Pemenuhan | Pesanan | `group_mtj_fulfillment` |
| `mtj.persediaan` | A-04 Petugas Persediaan | Persediaan | `group_mtj_stock_operator` |
| `mtj.peninjau.pesanan` | A-05 Koordinator atau Peninjau | Pesanan | `group_mtj_reviewer_order` |
| `mtj.peninjau.persediaan` | A-05 Koordinator atau Peninjau | Persediaan | `group_mtj_reviewer_stock` |
| `mtj.admin.uji` | A-06 Administrator Teknis Uji | Teknis | `group_mtj_technical_admin` |

Untuk menambahkan akun uji, klik **New/Baru** di **Akun dan Penugasan**, isi nama, login, peran dan lingkup, lalu simpan. Setelah menyetel kata sandi, akun aktif dapat masuk melalui login Odoo. Gunakan **Aktif** atau tindakan arsip untuk mengubah status. Akun nonaktif tersedia melalui filter **Nonaktif**. Tombol **Lihat Riwayat** menampilkan perubahan penugasan akun yang dipilih.

## Katalog dan pemetaan

A-06 menggunakan **Produk dan Pemetaan Satuan** untuk mengelola produk, satuan acuan, harga contoh, dan pemetaan. Akun prototipe dapat melihat daftar **Referensi Produk**, yang menampilkan produk aktif, SKU, varian, dan satuan. Data awal mencakup `WB-01` Rp100.000/roll, `BK-01` Rp2.500/pcs, dan `ZP-01` Rp5.000/pcs.

Contoh pemetaan Marketplace `ZP-01` berisi faktor `10` pcs per pack dan mulai dalam keadaan nonaktif. Mulai skenario pengecualian dengan pemetaan nonaktif. Untuk skenario koreksi, pilih filter **Nonaktif** dan aktifkan pemetaan setelah memeriksa dasar persetujuannya. Lakukan pengujian arsip pada produk uji terpisah jika SKU awal masih digunakan untuk demo.

## Kontrak untuk paket lain

- **Akses.** `mtj_prototype.group_mtj_user` memberi akses umum prototipe. Kedua grup A-05 mewarisi `mtj_prototype.group_mtj_reviewer`. Gunakan grup A-05 dengan akhiran `_order` atau `_stock` untuk keputusan di lingkup terkait. `mtj.account.assignment` memuat `user_id`, `role` (`a01`–`a06`), `scope` (`order`, `stock`, `technical`), dan `active`. Akun A-06 uji memakai grup aplikasi. Administrator bawaan Odoo diberi grup A-06 untuk penyiapan awal.
- **Catatan operasional.** Tambahkan ACL dan *record rule* pada model paket sendiri berdasarkan peran dan penugasan catatan. Periksa ACL, *record rule*, peran, dan prasyarat dalam setiap tindakan publik sebelum perubahan atau pengunduhan. Terapkan domain yang sama pada daftar, detail, laporan, dan ekspor. Hak teknis A-06 memberi akses pengelolaan prototipe. Gunakan akun berperan bisnis untuk menjalankan keputusan pesanan atau persediaan.
- **Produk.** `mtj.product` memuat `sku`, `name`, `variant`, `uom_id`, `sample_price` dalam rupiah, dan `active`. Gunakan `Many2one('mtj.product', ondelete='restrict')` dan panggil `_check_available_for_new_transaction()` saat memilih produk baru di server. Simpan satuan dan harga yang dipakai pada baris transaksi agar pembacaan historis tetap konsisten.
- **Pemetaan.** `mtj.uom.mapping` memuat `source`, `source_code`, `source_uom_id`, `product_id`, `reference_uom_id`, `factor`, `approval_basis`, dan `active`. Gunakan `_find_approved(source, source_code, source_uom)` dengan `source` bernilai `ketoko` atau `marketplace` dan `source_uom` berupa satu record `uom.uom`. Metode ini menghormati ACL dan mengembalikan record kosong jika pemetaan yang dapat dipakai tidak ada. Kuantitas acuan = kuantitas sumber × faktor. Simpan faktor yang benar-benar dipakai dan referensi pemetaannya pada hasil stok.
- **Audit.** Setelah tindakan berhasil dan seluruh pemeriksaan akses selesai, panggil `env['mtj.audit.event']._record(record, action, old_values=before, new_values=after, reason=reason)` dalam transaksi yang sama dengan pengguna asli. Kirim objek tersimpan dan nilai relevan yang dapat diserialisasi ke JSON. `res_model`, `res_id`, `actor_id`, dan `occurred_at` diisi oleh metode. A-06 dapat membaca audit akun. Paket riwayat menambahkan ACL baca dan domain sesuai catatan sumber sebelum menampilkan riwayat ke peran lain. Gunakan daftar field bukti yang eksplisit agar kredensial dan data pribadi tidak ikut tercatat.

## Pengujian

Jalankan instalasi bersih pada nama basis data uji tersendiri. Untuk mengulang pada basis data uji tersebut, ganti `-i` menjadi `-u`.

```sh
docker compose run --rm web odoo -d mtj_test -i mtj_prototype --test-tags /mtj_prototype --stop-after-init --without-demo=all
```

Pengujian modul mencakup login HTTP, penonaktifan akun, izin peran, audit penugasan, arsip katalog, dan pencarian pemetaan. Skenario akses per catatan pesanan dan stok serta validasi laporan dan ekspor dijalankan setelah paket terkait tersedia.

Verifikasi lokal pada 25 November 2026 memakai Odoo Community `17.0-20260908` dan PostgreSQL `16.15`. Delapan pengujian lulus saat instalasi bersih dan kembali lulus saat upgrade. Pemeriksaan browser mencakup pengaturan kata sandi, pembuatan dan perubahan penugasan oleh A-06, riwayat, penolakan akses langsung oleh A-05, dan penyuntingan harga contoh. Sesudah upgrade, tujuh akun seed tetap unik. Akun yang dibuat, perubahan lingkup, riwayat, serta harga yang disunting tetap tersimpan.
