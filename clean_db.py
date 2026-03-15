import json

# Define the target sections that a valid disease entry must have
TARGET_SECTIONS = [
    'симптомы', 'клиническая картина', 'признаки', 
    'жалобы', 'проявления', 'течение'
]

def clean_database(input_file: str, output_file: str):
    print(f"Loading database from {input_file}...")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {input_file}: {e}")
        return

    print(f"Original database size: {len(data)} entries.")

    cleaned_data = []
    
    for entry in data:
        # Check if any of the keys (sections) in the entry match any TARGET_SECTIONS
        # Note: keys in entry might be capitalized or differently cased, so we lowercase them for checking
        has_target_section = any(
            target in key.lower() 
            for key in entry.keys() 
            for target in TARGET_SECTIONS
        )
        
        if has_target_section:
            cleaned_data.append(entry)

    print(f"Cleaned database size: {len(cleaned_data)} entries.")
    
    print(f"Saving cleaned database to {output_file}...")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=4)
        print("Success! Database cleaned.")
    except Exception as e:
        print(f"Error saving to {output_file}: {e}")

if __name__ == "__main__":
    INPUT_DB = "disease_anamnesis_database.json"
    OUTPUT_DB = "disease_anamnesis_database_cleaned.json"
    clean_database(INPUT_DB, OUTPUT_DB)
