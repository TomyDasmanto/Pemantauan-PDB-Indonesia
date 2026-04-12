# Dashboard Model Framework (Streamlit + Plotly)

Folder ini berisi kerangka awal dashboard Streamlit yang meniru konsep pada gambar:

- Hasil Simulasi PDB & Kesejahteraan (bagian atas)
- Blok Makro (kiri)
- Accounting / PDB (tengah)
- Blok Moneter (kanan)
- Blok Fiskal (bawah tengah)

## File
- `app.py` -> aplikasi Streamlit utama
- `requirements.txt` -> dependensi
- `dashboard_template.xlsx` -> template workbook Excel yang dapat diisi nanti

## Menjalankan
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Struktur Excel yang dibaca
Workbook diharapkan memiliki sheet berikut:
- `simulasi`
- `makro`
- `pdb`
- `moneter`
- `fiskal`

Setiap sheet minimal memiliki kolom:
- `indikator`
- `baseline`
- `out_tw1`
- `out_tw2`
- `out_tw3`
- `out_tw4`
- `full_year`

Catatan: untuk saat ini dashboard hanya menampilkan 'rumah' / layout dan membaca data mentah dari Excel.
