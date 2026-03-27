# 🚜 AgriSim: Akıllı Tarımsal İlaçlama Simülasyonu

YOLOv8 tabanlı yabancı ot tespiti ve modern web dashboard arayüzüne sahip, **Webots R2025a** üzerinde geliştirilmiş hassas ilaçlama simülasyonu. Traktöre monte edilmiş 4 nozullu püskürtücü sistemi, bilgisayarlı görü kullanarak yabancı otları ekinlerden ayırır ve değişken oranlı ilaçlama (VRS) yapar.

## 🌟 Özellikler

*   **YOLOv8 Entegrasyonu:** Gerçek dünya veri setleri üzerinden eğitilmiş model ile anlık yabancı ot tespiti.
*   **Modern Dashboard:** FastAPI ve WebSocket tabanlı, gerçek zamanlı telemetri ve kamera görüntüsü sunan web arayüzü.
*   **Değişken Oranlı İlaçlama (VRS):** Tespit edilen yabancı otun güven skoruna göre nozul püskürtme şiddetinin otomatik ayarlanması.
*   **Otopilot Sistemi:** Şerit takip algoritması ile tarlada otonom sürüş.
*   **Tank Yönetimi:** Gerçek zamanlı sıvı tüketimi ve düşük tank seviyesi koruması.

## 🏗️ Proje Yapısı

```text
agri_simulation/
├── ai/
│   ├── dataset/          # Kamera kaynak görselleri (Kamera 1-4)
│   ├── models/           # Eğitilmiş YOLO (.pt) modelleri
│   └── yolo_detector.py  # YOLO çıkarım ve görselleştirme mantığı
├── controllers/
│   ├── spray_supervisor/ # Simülasyon beyni (Socket, AI, Görsel Efektler)
│   └── tractor_sprayer_controller/ # Traktör sürüş mantığı
├── ui/
│   ├── dashboard/        # Modern Web Dashboard (HTML/JS)
│   └── dashboard_backend.py # FastAPI WebSocket Köprüsü
├── config.py             # Merkezi konfigürasyon (Portlar, Hızlar, AI Ayarları)
└── worlds/
    └── agri_robot.wbt     # Ana Webots dünyası
```

## 🚀 Başlatma Talimatları

### 1. Hazırlık ve Kurulum

Öncelikle gerekli kütüphaneleri yüklemek için bir sanal ortam oluşturun:

```bash
# Sanal ortam oluştur (Windows)
python -m venv .venv
.\.venv\Scripts\activate

# Gerekli kütüphaneleri yükle
pip install -r requirements.txt
```

### 2. Webots Yapılandırması (Kritik)

Webots'un projedeki kütüphaneleri (ultralytics, opencv vb.) görebilmesi için:

1.  Webots'u açın.
2.  **Tools -> Preferences -> General** yolunu izleyin.
3.  **Python command** kısmına projenizdeki sanal ortamın yolunu yazın:
    `C:\...proje_yolu...\.venv\Scripts\python.exe`

### 3. Sistemi Çalıştırma

Sistem iki parçadan oluşur; simülasyon ve arayüz:

**A. Simülasyonu Başlatın:**
*   `worlds/agri_robot.wbt` dosyasını Webots ile açın ve simülasyonu "Run" moduna alın.

**B. Dashboard Backend'i Başlatın:**
*   Terminalinizde şu komutu çalıştırın:
    ```bash
    python -m uvicorn ui.dashboard_backend:app --host 0.0.0.0 --port 8000
    ```

**C. Dashboard'ı Açın:**
*   Tarayıcınızda `ui/dashboard/index.html` dosyasını açın (veya Live Server kullanın).
*   Sağ üstte "Connected" yazısını gördüğünüzde sistem hazırdır.

## 🎮 Kullanım Rehberi

*   **MANUEL:** Dashboard üzerindeki sliderlar ile traktörü sürebilir ve nozulları kontrol edebilirsiniz.
*   **AI MODE:** "YOLO AI" butonuna bastığınızda sistem veri setindeki resimler üzerinden tespit yapmaya başlar ve yabancı ot gördüğünde ilgili nozulu otomatik açar.
*   **AUTOPILOT:** "GPS Otonom Sürüş" butonuna bastığınızda traktör tarladaki şeritleri otomatik takip eder.

## 📋 Gereksinimler

*   Webots R2025a
*   Python 3.10+
*   Ultralytics (YOLOv8)
*   FastAPI & Uvicorn-Standard
*   OpenCV

