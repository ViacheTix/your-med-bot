import csv
import os
import re
from collections import defaultdict
import pymorphy2

morph = pymorphy2.MorphAnalyzer()

STOP_WORDS = {
    'в', 'на', 'с', 'и', 'а', 'но', 'или', 'у', 'к', 'о', 'от', 'из', 'для',
    'очень', 'сильно', 'немного', 'постоянно', 'иногда', 'периодически',
    'сегодня', 'вчера', 'утром', 'вечером', 'днем', 'ночью', 'это', 'что',
    'меня', 'у меня', 'уменя', 'есть', 'бывает', 'было', 'стало'
}

class DoctorRecommender:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.knowledge_base = self._load_knowledge_base()

    def _load_knowledge_base(self):
        knowledge_base = []
        if not os.path.exists(self.csv_path):
            print(f"Error: {self.csv_path} not found")
            return []
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8-sig') as file:
                fieldnames = ['disease', 'symptoms', 'treatment', 'doctor', 'urgency']
                reader = csv.DictReader(file, fieldnames=fieldnames)

                first_row = next(reader)
                if first_row['disease'] == 'заболевание':
                    pass
                else:
                    knowledge_base.append({
                        'disease': first_row['disease'],
                        'symptoms': first_row['symptoms'],
                        'doctor': first_row['doctor']
                    })

                for row in reader:
                    disease = row.get('disease', '').strip()
                    symptoms = row.get('symptoms', '').strip()
                    doctor = row.get('doctor', '').strip()
                    
                    if doctor and symptoms:
                        knowledge_base.append({
                            'disease': disease,
                            'symptoms': symptoms,
                            'doctor': doctor
                        })
        except Exception as e:
            print(f"Error loading knowledge base: {e}")
        
        return knowledge_base

    def normalize_word(self, word):
        word = re.sub(r'[^\w\-]', '', word.lower().strip())
        if not word or len(word) < 2 or word in STOP_WORDS:
            return None
        try:
            parsed = morph.parse(word)[0]
            return parsed.normal_form
        except:
            return word

    def split_into_words(self, text):
        words = re.findall(r'[а-яёa-z\-]+', text.lower())
        return words

    def symptoms_to_normalized_words(self, symptoms_string):
        words = self.split_into_words(symptoms_string)
        normalized = set()
        for word in words:
            norm_word = self.normalize_word(word)
            if norm_word:
                normalized.add(norm_word)
        return normalized

    def find_top_doctors(self, user_symptoms_list, top_n=3):
        """
        user_symptoms_list: List of symptoms (can be strings like 'насморк' or 'cough')
        """
        user_input_str = ", ".join(user_symptoms_list)
        user_symptoms_set = self.symptoms_to_normalized_words(user_input_str)
        
        doctor_ratings = defaultdict(float)
        
        for record in self.knowledge_base:
            doctor_symptoms_set = self.symptoms_to_normalized_words(record['symptoms'])
            common_symptoms = user_symptoms_set.intersection(doctor_symptoms_set)
            
            if len(doctor_symptoms_set) > 0:
                coverage_score = len(common_symptoms) / len(doctor_symptoms_set)
                relevance_score = len(common_symptoms) / len(user_symptoms_set) if user_symptoms_set else 0
                final_score = coverage_score * 0.4 + relevance_score * 0.6
                
                disease_words = self.symptoms_to_normalized_words(record['disease'])
                if user_symptoms_set.intersection(disease_words):
                    final_score += 0.2
            else:
                final_score = 0
            
            doctors = [d.strip() for d in record['doctor'].split(',')]
            for doctor in doctors:
                if final_score > doctor_ratings[doctor]:
                    doctor_ratings[doctor] = final_score
        
        sorted_doctors = sorted(doctor_ratings.items(), key=lambda x: x[1], reverse=True)
        return sorted_doctors[:top_n]

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), 'dataset_linnk_ai_zYvE_translated_ru-RU.csv')
recommender = DoctorRecommender(DEFAULT_CSV)
