# Watchguard Bot v3.0

Telegram üzerinden Windows bilgisayarlarınızı uzaktan izleyin ve yönetin.

## Kurulum

PowerShell'i **normal** açın (admin değil — script UAC ile kendisi yükselir):

```powershell
irm https://raw.githubusercontent.com/zygomatic-git/watchguard/main/install.ps1 -OutFile install.ps1; .\install.ps1
```

Kurulum menüsü açılır:

```
  [1]  Kur / Yeniden Kur
  [2]  Kaldir (Uninstall)
  [3]  Calisanlari Durdur
  [4]  Cikis
```

Kurulum sırasında şunlar istenir:
- **Bot Token** — [BotFather](https://t.me/BotFather)'dan `/newbot` ile alınır
- **Owner ID** — [userinfobot](https://t.me/userinfobot)'tan öğrenilir
- **Shell PIN** *(opsiyonel)* — `/shell` komutuna PIN koruması

## Gereksinimler

- Windows 10 / 11
- Python 3.10+ *(yoksa otomatik kurulur)*
- İnternet bağlantısı

## Komutlar

### 💻 Bilgisayar Yönetimi
| Komut | Açıklama |
|---|---|
| `/computers` | Bu bilgisayarın bilgilerini göster |
| `/ping` | Gecikme ve durum bilgisi |

### 📷 Görüntü
| Komut | Açıklama |
|---|---|
| `/ss` | Tüm monitörlerin ekran görüntüsü |
| `/rec` | 10 saniyelik ekran videosu |
| `/monitors` | Bağlı monitör listesi |

### 🖥️ Sistem
| Komut | Açıklama |
|---|---|
| `/myinfo` | CPU, RAM, disk, pil, uptime |
| `/window` | Aktif pencere başlığı |
| `/processes` | CPU+RAM'e göre top 20 işlem |
| `/killps <PID>` | İşlemi sonlandır |

### 🎙️ Mikrofon
| Komut | Açıklama |
|---|---|
| `/mic` | Varsayılan süre kaydı (10s) |
| `/mic 30` | 30 saniyelik kayıt |
| `/mic 2m` | 2 dakikalık kayıt |
| `/mic on` | Sürekli kayıt başlat (1 dk döngü) |
| `/mic off` | Sürekli kaydı durdur |

### ⚙️ Uzaktan Kontrol
| Komut | Açıklama |
|---|---|
| `/shell <komut>` | Kabuk komutu çalıştır |
| `/msg <metin>` | Ekranda mesaj kutusu göster (yanıt alınabilir) |
| `/lock` | Ekranı kilitle |
| `/restart` | Yeniden başlat (10s) |
| `/shutdown` | Kapat (10s) |

### 🔐 Güvenlik
| Komut | Açıklama |
|---|---|
| `/security` | Hareket algılama modunu aç/kapa |
| `/quiethours` | Sessiz saatleri aç/kapa (bildirim gönderilmez) |

### 📋 Log
| Komut | Açıklama |
|---|---|
| `/logs` | Son 30 log satırı |
| `/logs <n>` | Son n satır (maks 200) |
| `/clearlog` | Log geçmişini temizle |

### 🔄 Güncelleme
| Komut | Açıklama |
|---|---|
| `/update` | GitHub'tan en son sürümü indir ve uygula |

## Güncelleme

Telegram'dan `/update` komutu ile otomatik güncelleme yapılabilir.  
Manuel güncelleme için `install.ps1` menüsünden **[1] Kur / Yeniden Kur** seçin.

## Dosyalar

Kurulum sonrası diskte yalnızca şunlar kalır:

```
%APPDATA%\Microsoft\Windows\Themes\Watchguard\
  ├── watchguard_v3.pyw   ← obfüske edilmiş bot
  └── watchguard.dat      ← şifrelenmiş config (token, owner id, pin)
```

`install.ps1` kurulum tamamlandıktan sonra kendini siler.

## Birden Fazla Bilgisayar

Her bilgisayar için ayrı bir Telegram botu oluşturun:

1. `@BotFather` → `/newbot`
2. İsim verin: `Watchguard Ev`, `Watchguard İş` vb.
3. Her bilgisayarda kurulum sırasında o bilgisayara ait token'ı girin
