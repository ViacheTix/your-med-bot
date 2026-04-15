import json
import time
import pandas as pd
import wikipediaapi
from tqdm import tqdm

USER_AGENT = 'MedicalLLMDataBot/1.0 (contact: your_email@example.com)'
wiki_ru = wikipediaapi.Wikipedia(
    user_agent=USER_AGENT,
    language='ru',
    extract_format=wikipediaapi.ExtractFormat.WIKI
)

TARGET_SECTIONS = [
    'симптомы', 'клиническая картина', 'признаки', 
    'жалобы', 'проявления', 'течение'
]

def extract_relevant_info(page):
    """Extracts summary and relevant medical sections from a Wikipedia page."""
    if not page.exists():
        return None
    
    article_data = {
        "Summary": page.summary
    }
    
    for section in page.sections:
        section_title_lower = section.title.lower()
        if any(target in section_title_lower for target in TARGET_SECTIONS):
            article_data[section.title] = section.text
            
    return article_data

def main():
    input_file = 'data/query.json'
    print(f"Loading data from {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Total articles to process: {len(data)}")
    
    downloaded_data = []
    
    for row in tqdm(data, desc="Downloading Articles"):
        article_title = row.get('articleTitle')
        item_label = row.get('itemLabel')
        
        if not article_title:
            continue
            
        try:
            page = wiki_ru.page(article_title)
            extracted_info = extract_relevant_info(page)
            
            if extracted_info:
                extracted_info['Disease_Name'] = item_label
                extracted_info['Wikipedia_Title'] = article_title
                extracted_info['Wikidata_URL'] = row.get('item')
                
                downloaded_data.append(extracted_info)
                
        except Exception as e:
            print(f"\nError downloading {article_title}: {e}")
            
        time.sleep(0.5)
        
    output_file = 'data/disease_anamnesis_database.json'
    print(f"\nSaving {len(downloaded_data)} successfully downloaded articles to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(downloaded_data, f, ensure_ascii=False, indent=4)
        
    print("Download complete! Your LLM database is ready.")

if __name__ == "__main__":
    main()