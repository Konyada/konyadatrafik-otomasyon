# Konya'da Trafik — Otomatik Story Sistemi

@konyada_trafik Instagram hesabına ve Konya'da Trafik Facebook sayfasına her gün kendiliğinden
story atan sistem. GitHub'da ücretsiz çalışır, sunucu gerekmez. Paylaşım Meta'nın resmi API'siyle yapılır
(Facebook sayfasına story atmayı kapatmak için `config.yaml > facebook.story_paylas: false`).

## Ne paylaşır?

| Saat (İstanbul) | Story | Kaynak |
|---|---|---|
| 08:00 | Günün Sözü | `data/sozler.json` (124 söz, her gün sıradaki) |
| 08:45 | Nöbetçi eczaneler (Selçuklu · Meram · Karatay) | 5. Bölge Konya Eczacı Odası — konyanobetcieczaneleri.com (yedek: posta.com.tr) |
| 09:30 | Haber (genel) | Yapay zekâ + web araması |
| 11:30 | Haber (trafik / ulaşım) | Yapay zekâ + web araması |
| 12:30 | Haber (Selçuklu Belediyesi) | Selçuklu Belediyesi haberleri |
| 13:30 | Haber (Büyükşehir) | Yapay zekâ + web araması |
| 15:30 | Haber (genel) | Yapay zekâ + web araması |
| 17:30 | Haber (Konyaspor) | Yapay zekâ + web araması |
| 19:30 | Haber (genel) | Yapay zekâ + web araması |
| 23:50 | Vefat edenler (o günün tam listesi, günde tek story) | Konya Büyükşehir — mezarlik.konya.bel.tr |

Günde yaklaşık 10–12 story. Saatler, türler ve ilçeler `config.yaml` dosyasından değiştirilir.

Tasarımlar Konya'da Trafik'in kendi şablonlarıyla aynıdır: vefat ve nöbetçi eczane için koyu yeşil
zeminde ortada logo, "KONYA'DA BUGÜN" başlığı ve beyaz liste kartı; haber için üstte fotoğraf,
kırmızı ilçe ve yeşil kategori etiketi, başlık, kısa bilgi etiketleri, metin ve kapanış cümlesi.
Vefat ve nöbetçi eczane listeleri her zaman **tek story** olarak paylaşılır: liste uzadıkça satırlar
otomatik küçülür, çok kalabalık günlerde iki sütuna geçilir. Nöbetçi eczane listesi Eczacı Odası
sitesinden alınır; Oda sitesi telefonları otomatik erişime kapattığı için telefon, adres ve ilçe aynı Oda
verisini yayınlayan posta.com.tr listesinden eczane adıyla eşleştirilerek eklenir.

**Nasıl çalışır?** GitHub sistemi gündüz her 15 dakikada bir uyandırır. Sistem saati gelmiş ama
henüz yapılmamış görevi çalıştırır: veriyi çeker, yeşil şablonla 1080x1920 story görselini üretir,
görseli depodaki `gorseller` dalına koyar ve Instagram'a story olarak gönderir. Neyin paylaşıldığı
`data/durum.json` dosyasına yazılır; aynı vefat ya da haber iki kez paylaşılmaz. Veri henüz
güncellenmemişse (ör. eczane listesi 08:30'da değişmediyse) sistem 15 dakika sonra yeniden dener.

## Kurulum (bir kerelik)

### 1. GitHub deposu
1. github.com'da hesap açın (ya da yazılım ekibinin hesabını kullanın).
2. **New repository** → ad: `konyadatrafik-otomasyon` → **Public** seçin → oluşturun.
   (Public olmalı: Instagram story görselini bu depodaki adresten indirir. Şifreler depoda değil,
   gizli "Secrets" alanında durur.)
3. Bu klasördeki tüm dosyaları depoya yükleyin (`.github` klasörü dahil).
4. **Settings → Actions → General → Workflow permissions** → "Read and write permissions" → Save.

### 2. Logo, haber kaynakları ve fotoğraflar
- Logo `assets/logo.png` olarak eklendi. Değiştirmek için aynı adla kare, saydam PNG koyun.
- **Haberler önce abone olunan ajanslardan seçilir:** İHA, DHA ve AA'nın kendi sitelerindeki Konya
  haberleri ile Selçuklu Belediyesi'nin haberleri her haber saatinde okunur, yapay zekâ bunlardan
  uygun olanı seçip story metnini yazar. Listede uygun haber yoksa web araması yapılır.
  Kaynaklar `config.yaml > ajans` bölümünden eklenip çıkarılır (ör. Meram, Karatay belediyeleri).
  ANKA'nın sitesi otomatik okumaya uygun olmadığı için listede yok.
- **Haber fotoğrafı sırası:** ① haberin ajans ya da kurum fotoğrafı ("Foto: İHA" notuyla) →
  ② web haberi resmi bir kurum sitesindeyse o sayfanın fotoğrafı → ③ kendi arşiviniz
  (`assets/fotograflar/` ilçe/kategori klasörleri, ayrıntı `BENIOKU.txt`) → ④ yapay zekâ ile
  üretilen temsili görsel ("Temsili görsel" notuyla) → ⑤ arşivdeki `genel` klasörü.
  Hiçbiri yoksa haber fotoğrafsız tasarımla basılır.

### 3. Meta (Instagram) erişim anahtarı
Konya'da Trafik Facebook sayfası Ulusoy Dijital Medya portföyünde ve @konyada_trafik bu sayfaya bağlı olmalı (yapıldı).
1. developers.facebook.com → **Uygulamalarım → Uygulama oluştur** → tür: **İşletme** →
   işletme portföyü: **Ulusoy Dijital Medya**.
2. business.facebook.com → **Ayarlar → Kullanıcılar → Sistem kullanıcıları → Ekle**
   (ad: `konyadatrafik-bot`, rol: Yönetici).
3. Sistem kullanıcısına **Varlık ata**: Konya'da Trafik sayfası (tam kontrol), @konyada_trafik
   Instagram hesabı ve 1. adımdaki uygulama.
4. **Yeni token oluştur** → uygulamayı seçin → süre: **Asla sona ermez** → izinler:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`,
   `business_management`, `instagram_manage_messages`, `instagram_manage_comments`,
   `instagram_manage_insights`, `pages_manage_posts`, `pages_manage_metadata` → oluşturun ve token'ı kopyalayın.

### 4. Claude API anahtarı (haberler için)
platform.claude.com → **API Keys → Create Key** (hesaba ödeme yöntemi eklenmiş olmalı).

### 4b. Yapay zekâ görseli için Cloudflare (ücretsiz)
Temsili görseller Cloudflare Workers AI ile üretilir; günlük ücretsiz kota birkaç yüz görsele yeter.
1. dash.cloudflare.com'da hesap açın (ulusoydijitalmedya.com için açtıysanız onu kullanın).
2. Sağ menüdeki **Account ID** değerini kopyalayın.
3. **My Profile → API Tokens → Create Token → "Workers AI" şablonu** → oluşturun ve token'ı kopyalayın.

### 5. Anahtarları GitHub'a girin
Depoda **Settings → Secrets and variables → Actions → New repository secret**:

| Ad | Değer |
|---|---|
| `IG_ACCESS_TOKEN` | 3. adımdaki Meta token'ı |
| `ANTHROPIC_API_KEY` | 4. adımdaki Claude anahtarı |
| `CF_ACCOUNT_ID` | 4b. adımdaki Cloudflare Account ID |
| `CF_API_TOKEN` | 4b. adımdaki Cloudflare token'ı |
| `EDITORIAL_GUIDE` | (isteğe bağlı) haber üslubu talimatı — boşsa varsayılan üslup kullanılır |

Anahtarları kimseyle paylaşmayın, sadece bu alana girin.

### 6. İlk deneme
1. Depoda **Actions → Konya'da Trafik story → Run workflow** → komut: **kontrol** → çalıştırın.
   Kayıtta Instagram hesabının adı, veri kaynaklarının durumu görünür.
2. Aynı ekrandan komut: **soz**, "Deneme modu" işaretli → görsel üretilir ama paylaşılmaz.
   Çalışmanın özet sayfasında görsel bağlantısı çıkar.
3. Her şey yolundaysa sistem bir sonraki saatten itibaren kendiliğinden paylaşmaya başlar.
   Bütün sistemi bir süre paylaşımsız denemek isterseniz **Settings → Secrets and variables →
   Actions → Variables** bölümüne `DENEME_MODU` = `true` ekleyin; canlıya geçerken silin.

## Günlük kullanım
- **Ne paylaşıldı?** Actions sekmesindeki her çalışmanın özetinde görev, durum ve görsel bağlantısı var.
- **Elle story atmak:** Run workflow → komut seçin (soz, eczane, vefat, haber) → deneme işaretini kaldırın.
- **Hata olursa:** Çalışma kırmızı görünür ve GitHub e-posta ile haber verir. Aynı görev 3 kez hata
  verirse o gün için bırakılır.

## Maliyet
- GitHub (public depo), Meta Instagram API ve Cloudflare Workers AI (günlük ücretsiz kota içinde): ücretsiz.
- Claude API (günde 6 haber): `claude-sonnet-5-5` ile ayda yaklaşık 10–15 $, `config.yaml`'da
  `claude-haiku-5-5` seçilirse yaklaşık 5–6 $ (tahmini; çoğu web araması ücretidir).

## Yazılım ekibi için notlar
- Python 3.12. Testler: `pip install -r requirements.txt && python -m pytest -q`
- Örnek görseller (internetsiz): `python -m kt onizleme` → `cikti/onizleme/`
- Kod: `kt/kaynaklar/` (veri), `kt/render.py` (tasarım), `kt/instagram.py` (Graph API),
  `kt/gorsel_depo.py` (görsel barındırma), `kt/gorevler.py` (görevler), `kt/__main__.py` (zamanlama).
- Haber kuralları `kt/kaynaklar/haber.py` içinde: model yalnızca arama sonuçlarında gerçekten geçen
  bir kaynağı gösterebilir, aksi halde haber paylaşılmaz; kaza/suç haberlerinde isim verilmez;
  aynı haber tekrar paylaşılmaz.
- GitHub zamanlanmış çalışmaları yoğunlukta 5–20 dk gecikebilir; sistem 150 dk tolerans tanır.
- Public depolarda 60 gün hiç commit olmazsa GitHub zamanlamayı durdurur; sistem her gün
  `data/durum.json` commit ettiği için normalde sorun olmaz.
- Kaynak siteler yurt dışı IP'lerini engellerse `kontrol` komutu bunu gösterir. O durumda sistem
  Türkiye'deki bir sunucuda cron ile çalıştırılabilir (görseller için herkese açık bir klasör gerekir).
