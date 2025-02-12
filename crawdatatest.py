import hashlib
import os

import requests
import unicodedata
from bs4 import BeautifulSoup
import json
from time import sleep
import random
from datetime import datetime
from urllib.parse import urljoin
import re
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer, WordNetLemmatizer
from langdetect import detect
from collections import Counter
import json


class TextProcessor:
    def __init__(self):
        # Download required NLTK data
        # nltk.download('punkt')
        # nltk.download('stopwords')
        # nltk.download('wordnet')

        self.stemmer = PorterStemmer()
        self.lemmatizer = WordNetLemmatizer()
        try:
            with open('vietnamese-stopwords.txt', 'r', encoding='utf-8') as f:
                self.vietnamese_stopwords = set(f.read().splitlines())
        except FileNotFoundError:
            print("Warning: vietnamese-stopwords.txt not found. Creating empty stopwords set.")
            self.vietnamese_stopwords = set()
        self.english_stopwords = set(stopwords.words('english'))

    def remove_html_tags(self, text):
        """Remove HTML tags from text"""
        # Remove HTML tags
        clean = re.compile('<.*?>')
        text = re.sub(clean, '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text

    def clean_text(self, text):
        """Lowercase text and remove punctuation"""
        # Convert to lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text

    def detect_language(self, text):
        """Detect if text is in English or Vietnamese"""
        try:
            lang = detect(text)
            return 'vietnamese' if lang == 'vi' else 'english'
        except:
            return 'unknown'

    def tokenize_words(self, text, language):
        """Tokenize text into words and remove stopwords"""
        words = word_tokenize(text)
        # Select stopwords based on language
        stops = self.vietnamese_stopwords if language == 'vietnamese' else self.english_stopwords
        return [word for word in words if word.lower() not in stops]

    def get_word_frequency(self, words):
        """Count frequency of each word"""
        return Counter(words)

    def process_stems_and_lemmas(self, words):
        """Apply stemming and lemmatization to words"""
        stems = [self.stemmer.stem(word) for word in words]
        lemmas = [self.lemmatizer.lemmatize(word) for word in words]
        return {
            'stems': stems,
            'lemmas': lemmas
        }

    def split_into_sentences(self, text):
        """Split text into sentences"""
        return sent_tokenize(text)

    def sanitize_filename(self, text):
        """
        Convert to simple ASCII filename with hash to ensure uniqueness
        """
        # Create a hash of the original text to ensure uniqueness
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]

        # Remove diacritics and convert to ASCII
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ASCII', 'ignore').decode('ASCII')

        # Convert to lowercase and replace all non-alphanumeric chars with underscore
        text = re.sub(r'[^a-zA-Z0-9]', '_', text.lower())

        # Remove multiple underscores and limit length
        text = re.sub(r'_+', '_', text)
        text = text[:30].strip('_')

        # Add hash to ensure uniqueness
        return f"{text}_{text_hash}"

    def save_to_file(self, filename, content):
        """Save content to a file"""
        # with open(filename, 'w', encoding='utf-8') as f:
        #     f.write(content)
        # Sanitize the filename
        safe_filename = self.sanitize_filename(filename)

        # Create output directory if it doesn't exist
        output_dir = 'processed_articles'
        os.makedirs(output_dir, exist_ok=True)

        # Create full file path
        file_path = os.path.join(output_dir, safe_filename)

        # Save the file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Successfully saved: {file_path}")
        except Exception as e:
            print(f"Error saving file {file_path}: {e}")

    def process_article(self, article_data):
        """Process a single article"""
        # Get article content
        content = article_data.get('content', '')
        # Remove HTML tags
        clean_content = self.remove_html_tags(content)

        # Clean text
        processed_content = self.clean_text(clean_content)

        # Detect language
        language = self.detect_language(processed_content)

        # Tokenize words
        words = self.tokenize_words(processed_content, language)

        # Get word frequency
        word_freq = self.get_word_frequency(words)

        # Get stems and lemmas
        word_forms = self.process_stems_and_lemmas(words)

        # Split into sentences
        sentences = self.split_into_sentences(clean_content)

        # print(article_data.get('comments'))
        # Prepare results
        results = {
            'original_content': content,
            'clean_content': clean_content,
            'language': language,
            'word_count': len(words),
            'unique_words': len(set(words)),
            'word_frequency': dict(word_freq.most_common()),
            'stems': word_forms['stems'],
            'lemmas': word_forms['lemmas'],
            'sentences': sentences,
            'comments': article_data.get('comments', [])
        }

        # Save results to files
        article_title = article_data.get('title', 'article').replace(' ', '_')
        base_filename = f'processed_{article_title}'

        # Save main content
        self.save_to_file(f'{base_filename}_content.txt', clean_content)

        # Save analysis results
        with open(f'{base_filename}_analysis.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Save comments
        comments_text = '\n\n'.join([f"User: {c['user']}\nComment: {c['content']}\nLikes: {c['likes']}"
                                     for c in article_data.get('comments', [])])
        self.save_to_file(f'{base_filename}_comments.txt', comments_text)

        return results

class VnExpressScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.base_url = 'https://vnexpress.net'
        self.processed_urls = set()
        self.target_articles = 100
        self.text_processor = TextProcessor()

    def get_page_content(self, url):
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def extract_tags(self, soup):
        """Extract all available tags from the article"""
        tags = []

        # Method 1: Extract from breadcrumb
        try:
            breadcrumb = soup.find('ul', class_='breadcrumb')
            if breadcrumb:
                for item in breadcrumb.find_all('li'):
                    link = item.find('a')
                    if link:
                        tags.append({
                            'type': 'breadcrumb',
                            'text': link.text.strip(),
                            'url': urljoin(self.base_url, link.get('href', ''))
                        })
        except Exception as e:
            print(f"Error extracting breadcrumb tags: {e}")

        # Method 2: Extract from topic tags
        try:
            topic_tags = soup.find('div', class_='tags')
            if topic_tags:
                for tag in topic_tags.find_all('a', class_='item'):
                    tags.append({
                        'type': 'topic',
                        'text': tag.text.strip(),
                        'url': urljoin(self.base_url, tag.get('href', ''))
                    })
        except Exception as e:
            print(f"Error extracting topic tags: {e}")

        # Method 3: Extract from article metadata
        try:
            meta_keywords = soup.find('meta', {'name': 'keywords'})
            if meta_keywords:
                keywords = meta_keywords.get('content', '').split(',')
                for keyword in keywords:
                    keyword = keyword.strip()
                    if keyword:
                        tags.append({
                            'type': 'keyword',
                            'text': keyword,
                            'url': None
                        })
        except Exception as e:
            print(f"Error extracting meta keywords: {e}")

        # Method 4: Extract from related topics section
        try:
            related_topics = soup.find('div', class_='related-content')
            if related_topics:
                for topic in related_topics.find_all('a'):
                    tags.append({
                        'type': 'related',
                        'text': topic.text.strip(),
                        'url': urljoin(self.base_url, topic.get('href', ''))
                    })
        except Exception as e:
            print(f"Error extracting related topics: {e}")

        return tags

    def parse_article(self, article_soup, actual_url):
        try:
            title = article_soup.find('h1', class_='title-detail')
            description = article_soup.find('p', class_='description')
            content = article_soup.find('article', class_='fck_detail')
            publish_date = article_soup.find('span', class_='date')
            category = article_soup.find('meta', {'property': 'article:section'})
            author = article_soup.find('p', class_='author_mail')


            article_data = {
                'title': title.text.strip() if title else None,
                'description': description.text.strip() if description else None,
                'content': ' '.join([p.text.strip() for p in content.find_all('p')]) if content else None,
                'publish_date': publish_date.text.strip() if publish_date else None,
                'category': category.get('content') if category else None,
                'author': author.text.strip() if author else None,
                'tags': self.extract_tags(article_soup),
                'scrape_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            if article_data:
                article_id = self.extract_article_id(actual_url)
                if article_id:
                    article_data['comments'] = self.get_comments(article_id)
                    print("Comments fetched!", article_data['comments'])
                article_data['url'] = actual_url

            if article_data:
                # Process the article text
                processed_data = self.text_processor.process_article(article_data)

                # Add processed data to article data
                article_data.update({
                    'processed_data': processed_data
                })
            return article_data
        except Exception as e:
            print(f"Error parsing article: {e}")
            return None

    def get_comments(self, article_id):
        try:
            comments_url = f"https://usi-saas.vnexpress.net/index/get?offset=0&limit=100&sort=like&objectid={article_id}&objecttype=1&siteid=1000000"
            response = requests.get(comments_url, headers=self.headers)
            response.raise_for_status()

            comments_data = response.json()
            comments = []

            if 'data' in comments_data and 'items' in comments_data['data']:
                for comment in comments_data['data']['items']:
                    comments.append({
                        'content': comment.get('content', ''),
                        'user': comment.get('full_name', ''),
                        'likes': comment.get('userlike', 0),
                        'replies': comment.get('total_reply', 0),
                        'time': comment.get('time_created', '')
                    })

            return comments
        except Exception as e:
            print(f"Error fetching comments: {e}")
            return []

    def extract_article_id(self, url):
        try:
            return url.split('-')[-1].replace('.html', '')
        except Exception:
            return None

    def get_next_page_url(self, soup):
        try:
            pagination = soup.find('div', class_='pagination')
            if pagination:
                next_link = pagination.find('a', class_='next-page')
                if next_link and 'href' in next_link.attrs:
                    return urljoin(self.base_url, next_link['href'])
            return None
        except Exception as e:
            print(f"Error getting next page URL: {e}")
            return None

    def scrape_articles(self, category_url):
        articles = []
        current_url = category_url

        print(f"Starting to collect {self.target_articles} articles with tags...")

        while current_url and len(articles) < self.target_articles:
            print(f"\nProcessing page: {current_url}")
            page_content = self.get_page_content(current_url)

            if not page_content:
                break

            soup = BeautifulSoup(page_content, 'html.parser')
            article_links = soup.find_all(['h3', 'h2'], class_=['title-news', 'title_news'])

            for article_link in article_links:
                if len(articles) >= self.target_articles:
                    break

                link = article_link.find('a')
                if not link:
                    continue

                article_url = link.get('href')
                if not article_url or article_url in self.processed_urls:
                    continue

                self.processed_urls.add(article_url)

                print(f"\nProcessing article {len(articles) + 1}/{self.target_articles}")
                print(f"URL: {article_url}")

                sleep(random.uniform(1, 2))

                article_content = self.get_page_content(article_url)
                if not article_content:
                    continue

                article_soup = BeautifulSoup(article_content, 'html.parser')
                article_data = self.parse_article(article_soup, article_url)

                if article_data:
                    article_id = self.extract_article_id(article_url)
                    if article_id:
                        print("Fetching comments...")
                        article_data['comments'] = self.get_comments(article_id)
                    article_data['url'] = article_url

                    # Print found tags
                    if article_data['tags']:
                        print(f"Found {len(article_data['tags'])} tags:")
                        for tag in article_data['tags']:
                            print(f"- {tag['type']}: {tag['text']}")

                    articles.append(article_data)

                    if len(articles) % 10 == 0:
                        self.save_to_json(articles, f'vnexpress_articles_with_tags_{len(articles)}.json')
                        print(f"\nCheckpoint saved: {len(articles)} articles collected")

            if len(articles) < self.target_articles:
                current_url = self.get_next_page_url(soup)
                if current_url:
                    sleep(random.uniform(2, 3))

        return articles

    def save_to_json(self, articles, filename='vnexpress_articles.json'):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2)
            print(f"Data saved to {filename}")
        except Exception as e:
            print(f"Error saving data: {e}")


def main():
    scraper = VnExpressScraper()

    # Example: scrape from science category
    category_url = 'https://vnexpress.net/khoa-hoc'

    # Start scraping
    articles = scraper.scrape_articles(category_url)

    # Save final results
    final_filename = f'vnexpress_{len(articles)}_articles_with_tags_final.json'
    scraper.save_to_json(articles, final_filename)
    print(f"\nScraping completed! Collected {len(articles)} articles with tags.")


if __name__ == "__main__":
    main()