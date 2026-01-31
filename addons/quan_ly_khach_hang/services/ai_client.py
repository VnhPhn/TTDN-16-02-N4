import logging
import os
import requests
import json

_logger = logging.getLogger(__name__)


def analyze_sentiment(text, env=None, endpoint=None, api_key=None, timeout=6):
    """Call external sentiment API and return normalized result.

    Returns dict: {'label': 'positive'|'neutral'|'negative'|'unknown', 'score': float, 'explain': str}
    """
    # Resolve endpoint and api_key: priority -> explicit args -> env var -> ir.config_parameter -> default
    endpoint = endpoint or os.environ.get('QUAN_LY_KHACH_HANG_AI_ENDPOINT')
    api_key = api_key or os.environ.get('QUAN_LY_KHACH_HANG_AI_KEY')
    if env is not None:
        try:
            param = env['ir.config_parameter'].sudo()
            endpoint = endpoint or param.get_param('quan_ly_khach_hang.ai_endpoint')
            api_key = api_key or param.get_param('quan_ly_khach_hang.ai_key')
        except Exception:
            pass
    endpoint = endpoint or 'http://localhost:5000/api/sentiment'
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer %s' % api_key
    payload = {'text': text}
    # If OpenAI key provided (and no custom endpoint), use OpenAI Chat Completions
    openai_key = api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('QUAN_LY_KHACH_HANG_AI_KEY')
    # Only call OpenAI when an API key is provided AND the configured endpoint is NOT a local/mock endpoint.
    # This avoids accidentally routing to OpenAI when using a local mock service.
    is_local_endpoint = bool(endpoint and ('localhost' in endpoint or endpoint.startswith('http://localhost')))
    if openai_key and not is_local_endpoint:
        try:
            oa_headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {openai_key}'
            }
            prompt = (
                "You are a sentiment classifier. Given the user's text, return a JSON object with keys:\n"
                "label - one of 'positive','neutral','negative'\n"
                "score - a float between 0 and 1 representing confidence\n"
                "explain - a short (max 40 words) explanation.\n"
                "Respond with JSON only. Text: \"" + text.replace('"', '\\"') + "\""
            )
            body = {
                'model': 'gpt-3.5-turbo',
                'messages': [
                    {'role': 'system', 'content': 'You are a helpful assistant that only outputs JSON.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 200,
                'temperature': 0.0,
            }
            oa_resp = requests.post('https://api.openai.com/v1/chat/completions', headers=oa_headers, json=body, timeout=timeout)
            oa_resp.raise_for_status()
            j = oa_resp.json()
            content = j['choices'][0]['message']['content']
            try:
                data = json.loads(content)
            except Exception:
                # try to extract JSON substring
                import re
                m = re.search(r'\{.*\}', content, re.S)
                data = json.loads(m.group(0)) if m else {}
            label = (data.get('label') or 'unknown')
            score = float(data.get('score') or 0.0)
            explain = data.get('explain') or data.get('explanation') or ''
            return {'label': label, 'score': score, 'explain': explain}
        except Exception as exc:
            _logger.exception('OpenAI sentiment call failed: %s', exc)
            # fallback to local/mock endpoint if available

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json() or {}
        label = (data.get('label') or 'unknown')
        score = float(data.get('score') or 0.0)
        explain = data.get('explain') or data.get('explanation') or ''
        return {'label': label, 'score': score, 'explain': explain}
    except Exception as exc:
        _logger.exception('Failed calling sentiment API %s', exc)
        return {'label': 'unknown', 'score': 0.0, 'explain': str(exc)}
