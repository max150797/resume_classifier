import re
import os
import docx
import dateparser
import pymorphy3
import information

from pathlib import Path
from pymystem3 import Mystem
from pdfminer.high_level import extract_text
from urllib.parse import urlparse
from pprint import pprint
from datetime import datetime

DATA_PATH = 'data/'


class Parser:
    def __init__(self, data_path):
        self.data_path = data_path
        self.resumes = {}
        self.final_json = {}
        self.intervals = {}

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

    # Функция для преобразования PDF-файла в текст
    @staticmethod
    def convert_pdf_to_text(path_to_pdf):
        with open(path_to_pdf, 'rb') as file:
            text = extract_text(file)
            return text

    # Функция для преобразования DOCX-файла в текст
    @staticmethod
    def convert_docx_to_text(path_to_docx):
        with open(path_to_docx, 'rb') as file:
            text = ""
            document = docx.Document(file)
            for paragraph in document.paragraphs:
                text += " " + paragraph.text
            return text

    # нормализация текста
    @staticmethod
    def normalize_text_with_morph(text):
        morph = pymorphy3.MorphAnalyzer()
        words = text.split()
        normalized_words = [morph.parse(word)[0].normal_form for word in words]
        return ' '.join(normalized_words)

    # удаление лишних символов
    @staticmethod
    def preprocess_text(text):
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9а-яА-Я /._,@\-?=]', '', text)
        text = re.sub(r'Резюме обновлено (\d{1,2}) [а-яА-Я]+ \d{4} в \d{4}', '', text)
        text = text.replace('Ключевые ', '')

        return text.strip()

    # Функция для получения ФИО и города
    @staticmethod
    def get_mystem_info(text):
        m = Mystem()

        analyze = m.analyze(text)

        fio = {
            'last_name': '',
            'first_name': '',
            'middle_name': ''
        }

        city = ''

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
            elif 'гео' in analysis.get('gr', '') and city == '' and word[
                'text'].capitalize() not in information.countries:
                city = word['text'].capitalize()

        fio = f"{fio['last_name']} {fio['first_name']} {fio['middle_name']}".strip()

        return fio, city

    # Функция для получения даты рождения
    @staticmethod
    def get_birthday(text):
        birthday = re.search(
            r'(0?[1-9]|[12][0-9]|3[01]) (янв(?:аря)?|фев(?:раля)?|мар(?:та)?|апр(?:еля)?|мая|июн(?:я)?|июл(?:я)?|авг(?:уста)?|сен(?:тября)?|окт(?:ября)?|ноя(?:бря)?|дек(?:абря)?) ([12][0|9][0-9][0-9])',
            text.lower())

        if birthday:
            return dateparser.parse(birthday.group(), languages=['ru'])
        else:
            birthday = re.search(r'\d{2}[-.]\d{2}[-.]\d{4}', text.lower())
            if birthday:
                return datetime.strptime(birthday.group().replace('-', '.'), '%d.%m.%Y')
            else:
                return ''

    # Функция для получения возраста
    @staticmethod
    def get_age(birth_date):
        if birth_date != '':
            now = datetime.now()
            age = now.year - birth_date.year
            if now.month < birth_date.month or (now.month == birth_date.month and now.day < birth_date.day):
                age -= 1
            return age
        else:
            return ''

    # Функция для получения почты
    @staticmethod
    def get_mail(text):
        mail = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text)

        if mail:
            return mail.group()
        else:
            return ''

    # Функция для получения номера телефона (+7/7/8 - РФ номера)
    @staticmethod
    def get_phone_number(text):
        phone_number = re.search(r' (\+7|8|7).*?(\d{3}).*?(\d{3}).*?(\d{2}).*?(\d{2})', text)
        if phone_number:
            return phone_number.group().replace(' ', '').replace('-', '')
        else:
            return ''

    # Функция для получения гражданства
    @staticmethod
    def get_citizenship(text):
        words = text.upper().split(' ')
        try:
            index = words.index('ГРАЖДАНСТВО')
            val = text.split(' ')[index + 1]
            return 'РФ' if 'рос' in val.lower() else val
        except ValueError:
            return ''

    # Функция для поиска полезных ссылок
    @staticmethod
    def get_links(text):
        links = [urlparse(word).geturl() for word in text.split() if
                 any(prefix in word.lower() for prefix in ['http', 'www'])]
        return links if links else ''

    def get_intervals(self, text):

        self.intervals = {information.EDUCATION: [],
                          information.EXPERIENCE: [],
                          information.SKILLS: [],
                          information.ABOUT_ME: [],
                          information.QUALITY: [],
                          information.ADDITIONAL_INFORMATION: []}

        for target in self.intervals.keys():

            if target == information.ABOUT_ME:
                index = re.search(r'(обо\s+мне|о\s+себе)', text.lower())
            else:
                index = re.search(target, text.lower())

            if index:
                self.intervals[target] = [index.span()[0], index.span()[1] + 1]
            else:
                self.intervals[target] = [0, 0]

    def get_slice(self, parameter):
        vals = sorted(self.intervals.values())
        idx = vals.index(self.intervals[parameter])

        if idx == len(vals) - 1:
            return [vals[idx][1]]
        else:
            return [vals[idx][1], vals[idx + 1][0]]

    # Функция для получения скиллов
    def get_info_by_parametr(self, text, parameter):
        intervals = self.get_slice(parameter)
        if len(intervals) == 1:
            return text[intervals[0]:]
        else:
            return text[intervals[0]: intervals[1]]

    def fill_final_json(self):

        for file, info in self.resumes.items():
            print(file)

            self.get_intervals(info)

            fio, city = self.get_mystem_info(info)
            birthday_date = self.get_birthday(info)

            self.final_json[file] = {}
            self.final_json[file]['fio'] = fio
            self.final_json[file]['date'] = birthday_date.strftime('%d.%m.%Y') if birthday_date else ''
            self.final_json[file]['age'] = self.get_age(birthday_date) if birthday_date else ''
            self.final_json[file]['city'] = city
            self.final_json[file]['email'] = self.get_mail(info)
            self.final_json[file]['phone_number'] = self.get_phone_number(info)
            self.final_json[file]['citizenship'] = self.get_citizenship(info)
            self.final_json[file]['links'] = self.get_links(info)
            self.final_json[file]['education'] = self.get_info_by_parametr(info, information.EDUCATION)
            self.final_json[file]['experience'] = self.get_info_by_parametr(info, information.EXPERIENCE)
            self.final_json[file]['skills'] = self.get_info_by_parametr(info, information.SKILLS)
            self.final_json[file]['additional_information'] = self.get_info_by_parametr(info,
                                                                                        information.ADDITIONAL_INFORMATION)
            self.final_json[file]['about_me'] = self.get_info_by_parametr(info, information.ABOUT_ME)


if __name__ == '__main__':
    parser = Parser(DATA_PATH)
    parser.get_data()
    parser.fill_final_json()
    pprint(parser.final_json)
