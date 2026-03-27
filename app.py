import os
import re
import json
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import html
import time

def clean_transcript(text):
    import re

    # Extract only actual spoken text from JSON if present
    matches = re.findall(r'"utf8"\s*:\s*"([^"]+)"', text)

    if matches:
        text = ' '.join(matches)

    # Remove unwanted symbols but KEEP words
    text = re.sub(r'[^\w\s.,!?]', ' ', text)

    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()

load_dotenv()

app = Flask(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print("API KEY:", GEMINI_API_KEY)

def extract_video_id(youtube_url):
    """Extract video ID from YouTube URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, youtube_url)
        if match:
            return match.group(1)
    return None

def get_transcript_via_alternative_api(video_id):
    """Use alternative method to get transcript"""
    try:
        # Method 1: Try with oEmbed to get video info
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(oembed_url)
        
        # Method 2: Use a different transcript service
        # This uses the transcript API from a different endpoint
        transcript_url = f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&fmt=json3"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        response = requests.get(transcript_url, headers=headers)
        
        if response.status_code == 200 and response.text:
            try:
                data = response.json()
                transcript_text = ""
                
                if 'events' in data:
                    for event in data['events']:
                        if 'segs' in event:
                            for seg in event['segs']:
                                if 'utf8' in seg:
                                    transcript_text += seg['utf8'] + " "
                
                if transcript_text:
                    return transcript_text.strip()
            except:
                pass
        
        raise Exception("No transcript found")
        
    except Exception as e:
        print(f"Alternative API failed: {str(e)}")
        raise Exception("Could not fetch transcript")

def get_transcript_via_ytdl(video_id):
    """Use yt-dlp approach (most reliable)"""
    try:
        import subprocess
        import sys
        
        # Check if yt-dlp is installed
        try:
            import yt_dlp
        except ImportError:
            print("Installing yt-dlp...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
            import yt_dlp
        
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'skip_download': True,
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
            # Try to get subtitles
            if 'subtitles' in info and 'en' in info['subtitles']:
                subtitle_url = info['subtitles']['en'][0]['url']
                response = requests.get(subtitle_url)
                # Parse the subtitle content
                return clean_transcript(parse_vtt_subtitles(response.text))
            elif 'automatic_captions' in info and 'en' in info['automatic_captions']:
                caption_url = info['automatic_captions']['en'][0]['url']
                response = requests.get(caption_url)
                return clean_transcript(parse_vtt_subtitles(response.text))
            else:
                raise Exception("No English subtitles found")
                
    except Exception as e:
        print(f"yt-dlp method failed: {str(e)}")
        raise Exception(f"All methods failed: {str(e)}")

def parse_vtt_subtitles(vtt_content):
    """Parse WebVTT subtitle format"""
    import re
    
    # Remove WEBVTT header and metadata
    lines = vtt_content.split('\n')
    text_lines = []
    
    for line in lines:
        # Skip timestamps and metadata
        if '-->' in line or line.strip() == '' or line.strip().startswith('WEBVTT'):
            continue
        # Clean HTML tags
        line = re.sub(r'<[^>]+>', '', line)
        # Remove timestamp formatting
        line = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}', '', line)
        line = line.strip()
        
        if line and not line.isdigit():
            text_lines.append(line)
    
    return ' '.join(text_lines)

def get_transcript_final(video_id):
    """Main function to get transcript with multiple fallbacks"""
    
    # Method 1: Try direct YouTube timedtext API
    print("Method 1: Trying direct timedtext API...")
    try:
        transcript_url = f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&fmt=json3"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(transcript_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            transcript_text = ""
            if 'events' in data:
                for event in data['events']:
                    if 'segs' in event:
                        for seg in event['segs']:
                            if 'utf8' in seg:
                                transcript_text += seg['utf8'] + " "
            if transcript_text:
                print(f"Success! Got {len(transcript_text)} chars from timedtext API")
                return clean_transcript(transcript_text)
    except Exception as e:
        print(f"Method 1 failed: {str(e)}")
    
    # Method 2: Try with different language codes
    print("Method 2: Trying with language codes...")
    languages = ['en', 'en-US', 'en-GB', 'en-US', 'a.en']
    for lang in languages:
        try:
            transcript_url = f"https://www.youtube.com/api/timedtext?v={video_id}&lang={lang}&fmt=json3"
            response = requests.get(transcript_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                transcript_text = ""
                if 'events' in data:
                    for event in data['events']:
                        if 'segs' in event:
                            for seg in event['segs']:
                                if 'utf8' in seg:
                                    transcript_text += seg['utf8'] + " "
                if transcript_text:
                    print(f"Success with lang {lang}! Got {len(transcript_text)} chars")
                    return clean_transcript(transcript_text)
        except:
            continue
    
    # Method 3: Use yt-dlp (most reliable)
    print("Method 3: Trying yt-dlp...")
    try:
        return get_transcript_via_ytdl(video_id)
    except Exception as e:
        print(f"Method 3 failed: {str(e)}")
    
    raise Exception("Could not retrieve transcript from any method")

def generate_notes_with_gemini(transcript):
    """Generate notes using Gemini API with debug"""

    print("Using Gemini API...")

    if not GEMINI_API_KEY:
        print("No API key found → using fallback")
        return generate_fallback_notes(transcript)

    # Limit transcript size (important)
    if len(transcript) > 5000:
        transcript = transcript[:5000]

    prompt = f"""
You are a professional academic note-maker.

Convert the transcript into HIGH-QUALITY structured notes.

Strict rules:
- DO NOT copy sentences directly
- REMOVE jokes, fillers, and casual tone
- CONVERT into formal, exam-ready notes
- SHORT, precise bullet points
- GROUP related ideas
- USE clear headings

Format EXACTLY:

# Video Notes

## Main Topics
- Topic 1
- Topic 2

## Key Concepts
- Explanation
- Explanation

## Important Insights
- Insight
- Insight

## Summary
2-3 lines summary

Transcript:
{transcript}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2000
        }
    }

    endpoint = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    try:
        response = requests.post(endpoint, json=payload, timeout=30)

        # 🔥 DEBUG (THIS IS THE KEY FIX)
        print("Status Code:", response.status_code)
        print("Response Text:", response.text)

        if response.status_code == 200:
            data = response.json()

            if "candidates" in data and data["candidates"]:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                print("No candidates → fallback")

        else:
            print("Gemini failed → fallback")

    except Exception as e:
        print("Gemini error:", str(e))

    return generate_fallback_notes(transcript)

def generate_fallback_notes(transcript):
    """Simple fallback notes"""
    sentences = transcript.split('.')[:20]
    
    notes = f"""# Video Notes (Basic Summary)

## Key Points
"""
    for i, sent in enumerate(sentences[:15], 1):
        if sent.strip():
            notes += f"{i}. {sent.strip()}.\n"
    
    notes += f"\n## Summary\nThis video covers {len(sentences)} main points about the topic."
    
    return notes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_notes', methods=['POST'])
def generate_notes():
    try:
        data = request.get_json()
        youtube_url = data.get('youtube_url', '')
        
        if not youtube_url:
            return jsonify({'error': 'YouTube URL is required'}), 400
        
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        print(f"\nProcessing video: {video_id}")
        
        # ✅ STEP 1: Get transcript FIRST
        try:
            transcript = get_transcript_final(video_id)
        except Exception as e:
            print("Transcript fetch failed:", str(e))
            return jsonify({'error': 'Failed to fetch transcript'}), 500
        
        # ✅ STEP 2: Check transcript
        if not transcript or len(transcript) < 50:
            return jsonify({'error': 'Could not extract transcript'}), 400
        
        # ✅ STEP 3: Clean transcript (VERY IMPORTANT)
        transcript = clean_transcript(transcript)
        
        print(f"Transcript length: {len(transcript)}")
        
        # ✅ STEP 4: Generate notes
        notes = generate_notes_with_gemini(transcript)
        
        return jsonify({
            'success': True,
            'notes': notes,
            'video_id': video_id
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
if __name__ == '__main__':
        app.run(debug=True, port=5000)
