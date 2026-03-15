# Экстрактор медицинских данных (Vibe Hack)

Автоматизированный инструмент для извлечения медицинского анамнеза, симптомов и клинических описаний из русскоязычной Википедии для создания структурированной базы данных для обучения медицинских LLM.

## 🚀 Обзор

Этот проект реализует пайплайн для:
1. Чтения списка медицинских заболеваний из Wikidata/Wikipedia (`query.json`).
2. Скрапинга релевантных разделов (Симптомы, Клиническая картина, Жалобы и др.) с использованием API Википедии.
3. Генерации структурированной базы данных в формате JSON (`disease_anamnesis_database.json`), подходящей для дообучения (fine-tuning) нейросетей или создания медицинских RAG-систем.

## 📁 Структура проекта

- `data.py`: Основной Python-скрипт с логикой взаимодействия с API и обработки текста.
- `query.json`: Входной файл со списком заболеваний и метаданными из Wikidata.
- `disease_anamnesis_database.json`: Сгенерированный выходной файл с извлеченными данными.
- `README.md`: Документация проекта.

## Скачивание данных

[Ссылка для экстракции json из вики](https://query.wikidata.org/#SELECT%20%3Fitem%20%3FitemLabel%20%3FarticleTitle%20WHERE%20%7B%0A%20%20%3Fitem%20wdt%3AP31%2Fwdt%3AP279%2a%20wd%3AQ12136.%20%23%20Instance%20of%20%28or%20subclass%20of%29%20%22disease%22%0A%20%20%3Farticle%20schema%3Aabout%20%3Fitem.%0A%20%20%3Farticle%20schema%3AisPartOf%20%3Chttps%3A%2F%2Fru.wikipedia.org%2F%3E.%0A%20%20%3Farticle%20schema%3Aname%20%3FarticleTitle.%0A%20%20SERVICE%20wikibase%3Alabel%20%7B%20bd%3AserviceParam%20wikibase%3Alanguage%20%22ru%22.%20%7D%0A%7D)

```SQL
SELECT ?item ?itemLabel ?articleTitle WHERE {
  ?item wdt:P31/wdt:P279* wd:Q12136. # Instance of (or subclass of) "disease"
  ?article schema:about ?item.
  ?article schema:isPartOf <https://ru.wikipedia.org/>.
  ?article schema:name ?articleTitle.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ru". }
}
```

## 🛠 Установка

Рекомендуется использовать менеджер окружений **mamba** или **conda**.

### 1. Установка зависимостей

Установите библиотеку `wikipedia-api` и другие необходимые пакеты:

```bash
mamba install -c conda-forge wikipedia-api pandas tqdm
```

### 2. Настройка User Agent

Википедия требует наличия описательного User Agent. Откройте `data.py` и обновите переменную `USER_AGENT`:

```python
USER_AGENT = 'MedicalLLMDataBot/1.0 (контакт: your_email@example.com)'
```

## 📈 Использование

Запустите скрипт экстракции:

```bash
python data.py
```

Скрипт выполнит следующие действия:
- Загрузит список заболеваний из `query.json`.
- Извлечет краткое описание и разделы, соответствующие ключевым словам (например, "симптомы", "жалобы", "клиническая картина").
- Сохранит результат с задержкой (0.5 сек) между запросами, чтобы соблюдать правила использования серверов Википедии.

## 🔍 Схема данных

Итоговый файл `disease_anamnesis_database.json` имеет следующую структуру:

```json
[
    {
        "Summary": "Краткое описание заболевания...",
        "Симптомы": "Подробное описание симптомов...",
        "Disease_Name": "Название болезни",
        "Wikipedia_Title": "Заголовок статьи",
        "Wikidata_URL": "http://www.wikidata.org/entity/Q..."
    }
]
```

## ⚠️ Важное примечание

Экстрактор нацелен именно на разделы, связанные с **анамнезом** и **симптоматикой**. Если раздел существует в Википедии, но его название не совпадает со списком `TARGET_SECTIONS` в `data.py`, он будет пропущен. Это сделано для того, чтобы данные оставались сфокусированными на клинических проявлениях.