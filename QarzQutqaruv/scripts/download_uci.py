import os
import io
import zipfile
import urllib.request
import pandas as pd

def main():
    # URL архива согласно спецификации
    url = "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip"
    
    # Создаем папку data/raw, если ее нет
    raw_dir = os.path.join("data", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    
    print("Скачивание данных UCI...")
    response = urllib.request.urlopen(url)
    
    # Распаковываем ZIP-архив в памяти
    with zipfile.ZipFile(io.BytesIO(response.read())) as z:
        print("Чтение Excel файла...")
        # Читаем нужный файл, пропуская первую строку (header=1)
        with z.open("default of credit card clients.xls") as f:
            df = pd.read_excel(f, header=1)
    
    # Переименовываем целевую колонку 'default payment next month' в 'default'
    if 'default payment next month' in df.columns:
        df = df.rename(columns={'default payment next month': 'default'})
        
    # Сохраняем в CSV
    csv_path = os.path.join(raw_dir, "uci_credit.csv")
    df.to_csv(csv_path, index=False)
    
    print(f"Успешно! Данные сохранены в: {csv_path}")
    print(f"Размер данных: {df.shape[0]} строк, {df.shape[1]} колонок.")
    print(f"Колонки: {list(df.columns)}")

if __name__ == "__main__":
    main()