import os
import glob
import shutil
import random

def split_dataset(source_folder):
    # ── Dosya Yolları ──
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dataset_base = os.path.join(project_root, "ai", "dataset")
    
    camera_folders = [
        os.path.join(dataset_base, "camera_1"),
        os.path.join(dataset_base, "camera_2"),
        os.path.join(dataset_base, "camera_3"),
        os.path.join(dataset_base, "camera_4")
    ]
    
    # ── Hedef Klasörleri Oluştur ──
    for folder in camera_folders:
        os.makedirs(folder, exist_ok=True)
        
    # ── Görselleri Bul ──
    valid_extensions = [".jpg", ".jpeg", ".png"]
    images = []
    
    for ext in valid_extensions:
        images.extend(glob.glob(os.path.join(source_folder, f"*{ext}")))
        images.extend(glob.glob(os.path.join(source_folder, f"*{ext.upper()}")))
        
    if not images:
        print(f"HATA: '{source_folder}' içerisinde desteklenen formatta (.jpg, .png) görsel bulunamadı.")
        return
        
    print(f"Toplam {len(images)} adet görsel bulundu.")
    
    # Görselleri rastgele karıştır, böylece her kamera farklı sahneler görsün
    random.shuffle(images)
    
    # ── 4 Eşit Parçaya Böl ──
    chunk_size = len(images) // 4
    
    print("\nGörseller kopyalanıyor, lütfen bekleyin...\n")
    
    for i in range(4):
        start_idx = i * chunk_size
        # Sonuncu klasör kalan asimetrik tüm dosyaları alsın
        end_idx = (i + 1) * chunk_size if i < 3 else len(images)
        
        chunk = images[start_idx:end_idx]
        target_folder = camera_folders[i]
        
        for img_path in chunk:
            filename = os.path.basename(img_path)
            dest_path = os.path.join(target_folder, filename)
            # Orijinal dosyaya dokunmamak için copy kullanıyoruz
            shutil.copy2(img_path, dest_path)
            
        print(f"✅ Camera {i+1} klasörüne {len(chunk)} adet görsel kopyalandı.")
        
    print(f"\nİşlem Başarılı! Webots kameralarınız artık '{dataset_base}' altındaki resimleri kullanacak.")

if __name__ == "__main__":
    print("="*50)
    print("YOLO Veri Setini Webots Kameralarına Bölme Aracı")
    print("="*50)
    
    source = input("Ana veri seti (resimlerin bulunduğu) klasörün tam yolunu (path) yapıştırın:\n> ").strip()
    
    # Python Windows yollarındaki tırnak işaretlerini alabilir, bunları temizleyelim
    source = source.strip('"').strip("'")
    
    if os.path.isdir(source):
        split_dataset(source)
    else:
        print(f"HATA: '{source}' adında bir klasör bulunamadı. Yolu kontrol edip tekrar deneyin.")
