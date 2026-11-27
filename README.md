# tvlistesi — Türk ulusal kanal listesi

[![Kanal listesini guncelle](https://github.com/ailantus/TeVe/actions/workflows/update.yml/badge.svg)](https://github.com/ailantus/TeVe/actions/workflows/update.yml)

Türkiye genelinde yayın yapan ulusal kanalların **otomatik güncellenen** listesini üretir ve
izlemek için hazır bir oynatıcı arayüzü sunar. Hiçbir video dosyası barındırmaz; yalnızca
herkese açık yayın adreslerini derler.

## Nasıl çalışır?

1. `generate.py`, [`iptv-org/iptv`](https://github.com/iptv-org/iptv) projesinin saatlik
   güncellenen Türkiye listesini indirir (iki farklı adresten, biri yedek).
2. Yalnızca `config.json` içinde tanımlı ulusal kanalları seçer. Aynı kanalın birden çok
   yayın adresi varsa HTTPS, resmi CDN, çözünürlük ve 7/24 yayın kriterlerine göre
   en iyisini seçer; diğerlerini yedek olarak saklar.
3. Kaynakta sağlıklı adres yoksa kanal için tanımlanmış yedek adres kullanılır.
4. Şu dosyalar üretilir:

   | Dosya | Kullanım |
   | --- | --- |
   | `data/playlist.m3u` | IPTV oynatıcılar / TV kutu uygulamaları |
   | `data/channels.json` | JSON API (oynatıcı arayüzü bunu 30 dakikada bir yeniden okur) |
   | `data/channels.js` | `file://` ile açıldığında da çalışan gömülü veri |

## Film listesi

`data/power-sinema.m3u`, kaynaktaki film adlarının tür ve oyuncu fazlalıklarından
arındırılıp **`Film Adı (Yıl)`** biçimine getirilmiş ve IMDb tür verisiyle
sınıflandırılmış 9.342 filmlik listedir. Yıllar IMDb’den tamamlanmış, film
adlarında IMDb’nin Türkiye başlıkları kullanılmıştır (TR başlığı olmayanlar
kaynaktaki adla kalır).
Oynatıcıda doğrudan şu adresle açılabilir:

```
https://raw.githubusercontent.com/ailantus/TeVe/main/data/power-sinema.m3u
```

Türler `group-title` alanındadır: Aksiyon, Animasyon, Belgesel, Dram, Fantastik,
Gerilim, Gizem, Komedi, Korku, Macera, Müzik, Romantik, Savaş, Suç, Western, Aile,
Bilim Kurgu ve Diğer. Bu dosya saatlik kanal güncellemesinden etkilenmez.

## Depo yapısı

```
tvlistesi/
├── .github/workflows/update.yml   # saatlik otomatik güncelleme
├── data/                          # üretilen liste dosyaları (repo'ya dahil)
│   ├── playlist.m3u               # ulusal kanallar
│   └── power-sinema.m3u           # türlere göre sınıflandırılmış film listesi
├── config.json                    # kanal tanımları
├── generate.py                    # liste üretici (bağımlılık yok, Python 3)
├── index.html / style.css / app.js# izleme arayüzü
├── update_windows.ps1 / run.bat   # yerel güncelleme yardımcıları
└── README.md / LICENSE
```

## Hızlı başlangıç

Arayüzde kanal seçip izleyebilir, arama yapabilir, favori ekleyebilir ve kategori
filtreleyebilirsiniz. TV kutusunda ok tuşları ile kanallar arasında gezinebilir,
`Enter`/`OK` ile açabilirsiniz. Bir yayın açılmazsa **Yedek kaynağı dene** düğmesi
diğer adresleri sırayla dener.

## Otomatik güncelleme

### GitHub Actions (önerilen)

1. Bu klasör `ailantus/TeVe` deposunun kökü olacak şekilde yüklenir (içinde ayrıca
   bir `tvlistesi/` alt klasörü **olmamalı**).
2. `.github/workflows/update.yml` saatlik olarak listeyi yeniden üretip `data/` klasörünü
   commit eder. Eski `.github/workflows/main.yml` kaldırılmıştır; ikisi birlikte bırakılırsa
   aynı iş iki kez çalışır.
3. Depoda **Settings → Actions → General → Workflow permissions → Read and write** seçili
   olmalı; aksi halde bot listeyi commit edemez.
4. TV uygulamanıza playlist adresini verin:

   ```
   https://raw.githubusercontent.com/ailantus/TeVe/refs/heads/main/data/playlist.m3u
   ```

   Arayüzün JSON adresi (uygulama açılışta ve 30 dakikada bir buradan yeniler):

   ```
   https://raw.githubusercontent.com/ailantus/TeVe/refs/heads/main/data/channels.json
   ```

> Not: `https://ailantus.github.io/TeVe/` şu anda 404 dönüyor. Web arayüzünü
> tarayıcı/TV üzerinden açmak için depoda **Settings → Pages → Source: Deploy from a
> branch → main** seçeneğini etkinleştirin. Yerel `index.html` zaten uzak JSON'dan
> güncellenerek çalışır.

### Windows Görev Zamanlayıcı

```powershell
powershell -ExecutionPolicy Bypass -File .\update_windows.ps1
```

Bu komut `tvlistesi-kanal-guncelleme` adlı, saatte bir çalışan bir görev oluşturur.
Kaldırmak için:

```powershell
Unregister-ScheduledTask -TaskName "tvlistesi-kanal-guncelleme" -Confirm:$false
```

Tek seferlik güncelleme için `run.bat` dosyasını çalıştırın.

## Listeyi özelleştirme

`config.json` dosyasında:

- `channels` — kanal kimliği (`tvg-id`), görünen ad, kategori, logo, yedek adres ve
  kaynaktaki farklı adlar için `aliases`.
- `groups` — kategori sırası.
- `sources` — otomatik güncellenen kaynak listeleri (sırayla denenir).
- `logoBase` — logo dosyalarının bulunduğu adres.

Yeni kanal eklemek için `channels` dizisine bir girdi ekleyip `python generate.py`
çalıştırmanız yeterlidir.

## GitHub'a yükleme

Klasör bir Git deposu olarak hazırdır (`main` dalı, ilk commit atılmış durumda).
GitHub'da yeni bir depo açıp şunu çalıştırın:

```powershell
cd "C:\Users\Ahmet\Documents\Varsayılan Proje\tvlistesi"
git remote add origin https://github.com/<KULLANICI>/<DEPO>.git
git push -u origin main
```

Depo adı `ailantus/TeVe` dışında bir şeyse `app.js` ve `README.md` içindeki
`raw.githubusercontent.com/ailantus/TeVe/...` adreslerini yeni depo adına göre
değiştirin. `git push` kimlik bilgisi isterse GitHub Personal Access Token (repo
yetkisi) veya GitHub CLI (`gh auth login`) kullanın.

Alternatif olarak `tvlistesi-github.zip` dosyasını GitHub web arayüzünde
**Add file → Upload files** ile de yükleyebilirsiniz (içinde `.git` yoktur).

## Notlar

- Yayın adresleri üçüncü taraflara aittir; bazıları bölge kısıtlaması nedeniyle
  çalışmayabilir veya zamanla bozulabilir. Kaynak saatlik tarandığı için değişiklikler
  otomatik yansır.
- Bu proje içerik barındırmaz, yalnızca herkese açık bağlantıları listeler.
  İçerik hakları sahiplerine aittir.
