import re
import os
import docx
import dateparser
import datetime

from pathlib import Path
from pymystem3 import Mystem
from pdfminer.high_level import extract_text
from urllib.parse import urlparse
from pprint import pprint

DATA_PATH = 'data/'

class Parser():
    def __init__(self, data_path):
        self.data_path = data_path
        self.resumes = {}
        self.final_json= {}

    # Функция для преобразования PDF-файла в текст
    def convert_pdf_to_text(self, path_to_pdf):
        with open(path_to_pdf, 'rb') as file:
            text = extract_text(file)
            return text
        
    # Функция для преобразования DOCX-файла в текст
    def convert_docx_to_text(self, path_to_docx):
        with open(path_to_docx, 'rb') as file:
            text = ""
            document = docx.Document(file)
            for paragraph in document.paragraphs:
                text += " " + paragraph.text
            return text
    
    # удаление лишних символов
    def preprocess_text(self, text):
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9а-яА-Я /._,@\-?=]', '', text)
        return text.strip()
    
    # Функция для получения данных из файлов в указанной директории
    def get_data(self):
        for i, file in enumerate(os.listdir(DATA_PATH)):
            if Path(file).suffix == '.pdf':
                resume = self.convert_pdf_to_text(DATA_PATH + file)
            elif Path(file).suffix == '.docx':
                resume = self.convert_docx_to_text(DATA_PATH + file)
            else:
                resume = False
            
            if resume:
                self.resumes[f'{DATA_PATH}{file}_{i}'] = self.preprocess_text(resume)

    # Функция для получения ФИО и города
    def get_mystem_info(self, text):
        m = Mystem()

        #TODO как ускорить? объединять 10-20 пфдов в один файл и делать его анализ
        analyze = m.analyze(text)

        fio = {
            'last_name': '',
            'first_name': '',
            'middle_name': ''
        }

        city = ''
        countries = ['Россия', 'Казахстан', 'Украина', 'Беларусь'] # TODO можно заменить на список всех стран, чтобы нашелся именно город
        

        for word in analyze:
            try:
                analysis = word['analysis'][0]
            except (KeyError, IndexError):
                continue

            if 'имя' in analysis.get('gr', '') and not fio['first_name']:
                fio['first_name'] = word['text'].capitalize()
            elif 'фам' in analysis.get('gr', '') and not fio['last_name']:
                fio['last_name'] = word['text'].capitalize()
            elif 'отч' in analysis.get('gr', '') and not fio['middle_name']:
                fio['middle_name'] = word['text'].capitalize()
            elif 'гео' in analysis.get('gr', '') and city == '' and word['text'].capitalize() not in countries:
                city = word['text'].capitalize()

        fio = ' '.join(fio.values()).strip()

        return fio, city
    
    # Функция для получения даты рождения
    def get_birthday(self, text):
        birthday = re.search(r'(0?[1-9]|[12][0-9]|3[01]) (янв(?:аря)?|фев(?:раля)?|мар(?:та)?|апр(?:еля)?|мая|июн(?:я)?|июл(?:я)?|авг(?:уста)?|сен(?:тября)?|окт(?:ября)?|ноя(?:бря)?|дек(?:абря)?) ([12][0|9][0-9][0-9])', text.lower())

        if birthday:
            return dateparser.parse(birthday.group(), languages=['ru'])
        else:
            return None
    
    # Функция для получения возраста
    def get_age(self, birth_date):
        now = datetime.datetime.now()
        age = now.year - birth_date.year
        if now.month < birth_date.month or (now.month == birth_date.month and now.day < birth_date.day):
            age -= 1
        return age


    # Функция для получения почты
    def get_mail(self, text):
        mail = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text)

        if mail:
            return mail.group()
        else:
            return None

    # Функция для получения номера телефона (+7/7/8 - РФ номера)
    def get_phone_number(self, text):
        phone_number = re.search(r' (\+7|8|7).*?(\d{3}).*?(\d{3}).*?(\d{2}).*?(\d{2})', text)
        if phone_number:
            return phone_number.group().replace(' ', '').replace('-','')
        else:
            return None
        
    # Функция для получения гражданства
    def get_citizenship(self, text):
        words = text.upper().split(' ')
        try:
            index = words.index('ГРАЖДАНСТВО')
            val = text.split(' ')[index+1]
            return 'РФ' if 'рос' in val.lower() else val
        except ValueError:
            return ''
    
    # Функция для поиска полезных ссылок
    def get_links(self, text):
        links = [urlparse(word).geturl() for word in text.split() if any(prefix in word.lower() for prefix in ['http', 'www'])]
        return links if links else None


    def fill_final_json(self):

        for file, info in self.resumes.items():
            print(file)

            fio, city = self.get_mystem_info(info)
            birthday_date = self.get_birthday(info[:500])

            self.final_json[file] = {}
            self.final_json[file]['fio'] = fio
            self.final_json[file]['date'] = birthday_date.strftime('%d.%m.%Y') if birthday_date else ''
            self.final_json[file]['age'] = self.get_age(birthday_date) if birthday_date else ''
            self.final_json[file]['city'] = city
            self.final_json[file]['email'] = self.get_mail(info)
            self.final_json[file]['phone_number'] = self.get_phone_number(info)
            self.final_json[file]['citizenship'] = self.get_citizenship(info)
            self.final_json[file]['links'] = self.get_links(info)

            #TODO добавить:
            # Образование: Название учебного заведения, степень образования, специализация, даты обучения.
            # Опыт работы: Название компании, должность, даты работы, обязанности.
            # Навыки: Список профессиональных навыков и компетенций.
            # Дополнительная информация: Проекты, достижения, сертификаты

        
            
if __name__ == '__main__':
    parser = Parser(DATA_PATH)
    parser.get_data()
    parser.fill_final_json()
    pprint(parser.final_json)