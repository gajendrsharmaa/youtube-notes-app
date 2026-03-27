import yt_dlp

def get_transcript(video_url):
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'subtitleslangs': ['en'],
        'quiet': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

        if 'subtitles' in info and 'en' in info['subtitles']:
            subtitle_url = info['subtitles']['en'][0]['url']

            import requests
            res = requests.get(subtitle_url)

            return res.text
        else:
            return "No subtitles found"

print(get_transcript("https://www.youtube.com/watch?v=8jPQjjsBbIc"))