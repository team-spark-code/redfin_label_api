from dotenv import load_dotenv ; load_dotenv()
import json
import yake

# Yake 키워드 추출 (scraped_news_tagging_ollama.ipynb 참고)
def extract_keywords_yake(input_file, output_file, top_k: int = 10):
    kw_extractor = yake.KeywordExtractor(top=top_k, stopwords=None)

    with open(input_file, 'r', encoding='utf-8') as infile, \
        open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            try:
                entry = json.loads(line.strip())
                text = (entry.get('title', '') + " " + entry.get('description', '')).strip()
                if text:
                    keywords = [kw for kw, score in kw_extractor.extract_keywords(text)]
                else:
                    keywords = []
                entry['keywords'] = keywords
                json.dump(entry, outfile, ensure_ascii=False)
                outfile.write('\n')
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON line: {e}")
            except Exception as e:
                
                print(f"Error processing line: {e}")

    print(f"Keywords extracted and saved to {output_file}")


def extract_keywords_from_text(title: str, content: str, top_k: int = 10):
    """
    단일 문자열에서 키워드 추출 (simple_processor 호환용)
    """
    text = (title + " " + content).strip()
    if not text:
        return []
    try:
        kw_extractor = yake.KeywordExtractor(top=top_k, stopwords=None)
        return [kw for kw, _ in kw_extractor.extract_keywords(text)]
    except Exception:
        return []
