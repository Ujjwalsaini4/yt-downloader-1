# app.py
# -*- coding: utf-8 -*-
import os
import time
import tempfile
import shutil
import threading
import uuid
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify, render_template_string, abort, send_file
from shutil import which
from yt_dlp import YoutubeDL

# ---------- CONFIG ----------
DEBUG_LOG = os.environ.get("DEBUG_LOG", "") not in ("", "0", "false", "False")
PORT = int(os.environ.get("PORT", 5000))
APP_PREFIX = os.environ.get("APP_PREFIX", "Hyper_Downloader")
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", 60 * 60))  # 1 hour default
DOWNLOAD_KEEP_SECONDS = int(os.environ.get("DOWNLOAD_KEEP_SECONDS", 60))  # 60s after fetch
CLEANUP_INTERVAL = int(os.environ.get("CLEANUP_INTERVAL", 60 * 10))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", 3))  # limit concurrent downloads

app = Flask(__name__)

# Save cookies if present (from environment)
cookies_data = os.environ.get("COOKIES_TEXT", "").strip()
if cookies_data:
    try:
        with open("cookies.txt", "w", encoding="utf-8") as f:
            f.write(cookies_data)
    except Exception:
        pass


def ffmpeg_path():
    # prefer which, then common paths
    p = which("ffmpeg")
    if p:
        return p
    for candidate in ("/usr/bin/ffmpeg", "/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(candidate).exists():
            return candidate
    return None


_FFMPEG = ffmpeg_path()
if _FFMPEG:
    HAS_FFMPEG = True
else:
    HAS_FFMPEG = False

if DEBUG_LOG:
    print(f"[DEBUG] ffmpeg found: {HAS_FFMPEG} (path={_FFMPEG})")

# ---------- HTML (SEO + legal + responsive navbar) ----------
HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />

<!-- Google Search Console verification -->
<meta name="google-site-verification" content="QYJJCjvAqrNJt6dOIKPbj_8jnL2m_nC52WBsOPgSTpQ" />

<!-- Basic SEO -->
<meta name="description" content="Free online video downloader for YouTube, Instagram, Facebook, Twitter, TikTok and Dailymotion. Download MP4 or MP3 in HD quality with Hyper Downloader.">

<!-- Indexing & canonical -->
<meta name="robots" content="index,follow" />
<link rel="canonical" href="https://yt-downloader-s52z.onrender.com/" />

<!-- Open Graph (social share) -->
<meta property="og:title" content="YouTube & Instagram Video Downloader Online | Hyper Downloader">
<meta property="og:description" content="Download YouTube, Instagram, Facebook, Twitter, TikTok and Dailymotion videos as MP4 or MP3. Fast, free and easy-to-use online video downloader.">
<meta property="og:url" content="https://yt-downloader-s52z.onrender.com/">
<meta property="og:type" content="website">

<title>YouTube Video Downloader Online | Hyper Downloader</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#050b16;
  --card:#0a162b;
  --muted:#a3b5d2;
  --grad1:#2563eb;
  --grad2:#06b6d4;
  --accent:linear-gradient(90deg,var(--grad1),var(--grad2));
  --radius:16px;
  --pill-bg: rgba(255,255,255,0.03);
  --pill-border: rgba(255,255,255,0.06);
}
*{box-sizing:border-box;}
body{
  margin:0;
  background:radial-gradient(1200px 800px at 30% 20%,rgba(37,99,235,.08),transparent),
             radial-gradient(1000px 600px at 80% 90%,rgba(6,182,212,.1),transparent),
             var(--bg);
  color:#e8f0ff;
  font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,"Noto Sans",sans-serif;
  -webkit-font-smoothing:antialiased;
  padding:clamp(12px,2vw,24px);
}

.instagram-text {
    background: radial-gradient(circle at 30% 107%, #fdf497 0%, #fdf497 5%, #fd5949 45%, #d6249f 60%, #285AEB 90%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    text-fill-color: transparent;
}

.wrap{max-width:960px;margin:auto;}
h1,h2,h3{margin:0;font-weight:800;}
h2{font-size:22px;}
.small{font-size:13px;color:var(--muted);}

/* HEADER + NAVBAR */
header{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
  background:rgba(255,255,255,0.02);
  border:1px solid rgba(255,255,255,0.05);
  padding:12px 18px;
  border-radius:var(--radius);
  box-shadow:0 6px 24px rgba(0,0,0,.3);
  backdrop-filter:blur(8px) saturate(120%);
  position:sticky;
  top:clamp(8px,1.5vw,16px);
  z-index:30;
}
.brand{display:flex;align-items:center;gap:12px;}
.logo{
  width:52px;height:52px;border-radius:14px;
  background:var(--accent);
  display:grid;place-items:center;
  color:#fff;font-weight:800;font-size:18px;
  box-shadow:0 8px 24px rgba(6,182,212,.25);
}
.logo { animation: bgPulse 8s ease-in-out infinite; }
@keyframes bgPulse {
  0% { filter: hue-rotate(0deg) saturate(100%); }
  50% { filter: hue-rotate(8deg) saturate(110%); }
  100% { filter: hue-rotate(0deg) saturate(100%); }
}
.brand-title span{
  background:var(--accent);
  -webkit-background-clip:text;
  color:transparent;
}

/* MAIN NAV (desktop) */
.nav-desktop{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  justify-content:flex-end;
}
.nav-desktop a{
  font-size:12px;
  padding:6px 10px;
  border-radius:999px;
  text-decoration:none;
  color:var(--muted);
  border:1px solid rgba(255,255,255,0.06);
  background:rgba(255,255,255,0.02);
  display:inline-flex;
  align-items:center;
  gap:6px;
  transition:background .15s ease,border-color .15s ease,transform .08s ease,color .15s ease;
}
.nav-desktop a span.icon{
  font-size:13px;
}
.nav-desktop a:hover{
  background:var(--accent);
  border-color:transparent;
  color:#fff;
  transform:translateY(-1px);
}
.nav-desktop a.active{
  background:var(--accent);
  color:#fff;
  border-color:transparent;
}

/* MOBILE HAMBURGER */
.nav-toggle{
  display:none;              /* default hidden: desktop */
  width:36px;
  height:36px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,0.12);
  background:rgba(5,11,22,0.9);
  align-items:center;
  justify-content:center;
  cursor:pointer;
  padding:0;
}

.nav-toggle span{
  position:relative;
  width:18px;
  height:2px;
  border-radius:999px;
  background:#e5ecff;
  display:block;
}

/* 3 lines (upper + lower) */
.nav-toggle span::before,
.nav-toggle span::after{
  content:"";
  position:absolute;
  left:0;
  width:18px;
  height:2px;
  border-radius:999px;
  background:#e5ecff;
  transition:transform .18s ease, opacity .18s ease;
}

/* upper line */
.nav-toggle span::before{
  transform:translateY(-6px);
}

/* lower line */
.nav-toggle span::after{
  transform:translateY(6px);
}

/* open state => cross (X) */
.nav-toggle.open span{
  background:transparent;
}
.nav-toggle.open span::before{
  transform:rotate(45deg);
}
.nav-toggle.open span::after{
  transform:rotate(-45deg);
}


/* MOBILE NAV PANEL (fixed) */
.nav-panel{
  display:none;
  position:fixed;
  left:0;
  right:0;
  top:100px;           /* agar thoda upar/neeche chahiye ho to 76/84 try kar sakte ho */
  z-index:40;
  padding:0 16px;
}

.nav-panel-inner{
  background:rgba(5,11,22,0.98);
  border-radius:var(--radius);
  border:1px solid rgba(255,255,255,0.08);
  box-shadow:0 18px 40px rgba(0,0,0,0.8);
  padding:14px 12px 16px;    /* top-bottom zyada */
  backdrop-filter:blur(10px);
}

.nav-panel a{
  display:flex;
  align-items:center;
  gap:8px;
  padding:10px 12px;        /* button thoda mota */
  border-radius:10px;
  text-decoration:none;
  font-size:13px;
  color:var(--muted);
  border:1px solid transparent;
  margin-bottom:4px;
}

.nav-panel a:last-child{
  margin-bottom:0;
}
.nav-panel a:hover{
  background:rgba(37,99,235,0.25);
  border-color:rgba(37,99,235,0.5);
  color:#e5ecff;
}
.nav-panel a.active{
  background:var(--accent);
  border-color:transparent;
  color:#fff;
}

/* MAIN CARD */
.card{
  background:rgba(255,255,255,0.02);
  border:1px solid rgba(255,255,255,0.05);
  border-radius:var(--radius);
  box-shadow:0 8px 32px rgba(0,0,0,.4);
  padding:clamp(16px,3vw,28px);
  margin-top:20px;
  transition:transform .2s ease,box-shadow .3s ease;
}
.card:hover{transform:translateY(-4px);box-shadow:0 14px 40px rgba(0,0,0,.6);}

label{display:block;margin-bottom:6px;color:var(--muted);font-size:13px;}
input,select,button{
  width:100%;padding:12px 14px;border-radius:12px;
  border:1px solid rgba(255,255,255,0.07);
  background-color:#0d1c33;color:#e8f0ff;
  font-size:15px;
}
input::placeholder{color:#5a6b8a;}
button{
  background:var(--accent);border:none;font-weight:700;color:#fff;
  box-shadow:0 8px 28px rgba(6,182,212,.25);
  cursor:pointer;transition:transform .08s;
}
button:active{transform:scale(.98);}
button[disabled]{opacity:.6;cursor:not-allowed;}

.grid{display:grid;gap:12px;margin:10px 0px;}
@media(min-width:700px){.grid{grid-template-columns:2fr 1fr 1.2fr 1.2fr auto;align-items:end;}}
.full{grid-column:1/-1;}

.progress{
  margin-top:14px;height:14px;border-radius:999px;
  background:rgba(255,255,255,0.04);
  overflow:hidden;position:relative;
}
.bar{
  width:0%;height:100%;
  background:var(--accent);
  transition:width .3s ease;
  box-shadow:0 0 20px rgba(6,182,212,.4);
}
.pct{
  position:absolute;left:50%;top:50%;
  transform:translate(-50%,-50%);
  color:#fff;font-weight:700;font-size:13px;
  text-shadow:0 1px 2px rgba(0,0,0,0.5);
}
.bar::after{
  content:"";
  position:absolute;inset:0;
  background:linear-gradient(90deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02), rgba(255,255,255,0.06));
  transform:translateX(-40%);opacity:0.6;filter:blur(6px);
  animation: sheen 2.4s linear infinite;
}
@keyframes sheen{100%{transform:translateX(120%)}}
.status-row{
  display:flex;align-items:center;justify-content:space-between;margin-top:10px;gap:12px;
}
.status-left{color:var(--muted);font-size:13px;display:flex;align-items:center;gap:8px;}
.eta-pill{
  display:inline-flex;align-items:center;gap:10px;padding:8px 12px;border-radius:999px;
  background:var(--pill-bg);border:1px solid var(--pill-border);font-weight:700;font-size:13px;color:#fff;
  min-width:90px;justify-content:center;
  box-shadow:0 6px 18px rgba(6,182,212,0.06);
}
.eta-pill .label{opacity:0.85;color:var(--muted);font-weight:600;font-size:12px;margin-right:6px}
.eta-pill .value{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Roboto Mono,monospace;font-weight:800}

.preview{
  display:none;margin-top:10px;padding:10px;
  background:rgba(255,255,255,0.02);
  border-radius:12px;border:1px solid rgba(255,255,255,0.05);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.03);
}
.preview-row{display:flex;gap:10px;align-items:center;}
.thumb{width:120px;height:68px;border-radius:8px;object-fit:cover;background:#081627;}
.meta .title{font-weight:700;font-size:15px;}
.meta .sub{color:var(--muted);font-size:13px;margin-top:4px;}

/* INFO / CONTENT SECTIONS BELOW MAIN CARD */
.section-title{
  font-size:20px;
  margin-bottom:6px;
}
.section-text{
  font-size:14px;
  color:var(--muted);
  line-height:1.6;
}

/* HOW TO USE */
.howto-grid{
  display:grid;
  gap:16px;
  margin-top:16px;
}
@media(min-width:720px){
  .howto-grid{
    grid-template-columns:repeat(3, minmax(0,1fr));
  }
}
.howto-item{
  padding:14px;
  border-radius:14px;
  background:rgba(255,255,255,0.02);
  border:1px solid rgba(255,255,255,0.05);
}
.howto-badge{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:32px;
  height:32px;
  border-radius:999px;
  background:var(--accent);
  font-size:14px;
  font-weight:700;
}
.howto-illus{
  margin-top:10px;
  height:90px;
  border-radius:12px;
  background:#050b16;
  position:relative;
  overflow:hidden;
}
/* naya: image ko nicely fit karne ke liye */
.howto-illus img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}

/* FEATURE LISTS */
.badge-row{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin:12px 0 4px;
}
.badge{
  font-size:11px;
  padding:5px 10px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,0.08);
  background:rgba(255,255,255,0.02);
  color:var(--muted);
}
.list{
  margin:8px 0 0;
  padding-left:18px;
  font-size:14px;
  color:var(--muted);
}
.list li{margin-bottom:4px;}

/* FAQ */
.faq-item{
  margin-top:10px;
  padding-top:10px;
  border-top:1px solid rgba(255,255,255,0.06);
}
.faq-q{
  font-weight:600;
  font-size:14px;
}
.faq-a{
  font-size:13px;
  color:var(--muted);
  margin-top:4px;
}

/* FOOTER */
footer{
  margin-top:20px;
  text-align:center;
  color:var(--muted);
  font-size:12px;
}
.footer-links{
  display:flex;
  flex-wrap:wrap;
  justify-content:center;
  gap:10px;
  margin-bottom:6px;
}
.footer-links a{
  color:var(--muted);
  text-decoration:none;
  font-size:12px;
}
.footer-links a:hover{
  text-decoration:underline;
}

/* RESPONSIVE */
@media(max-width:720px){
  header{
    gap:10px;
  }
  .nav-desktop{
    display:none;
  }
  .nav-toggle{
    display:inline-flex;
    margin-left:auto;
  }
  .nav-panel.open{
    display:block;
  }
}
@media(max-width:520px){
  .eta-pill{min-width:72px;padding:6px 10px;font-size:12px}
  .brand-title h1{font-size:18px}
}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="brand">
    <div class="logo">HD</div>
    <div class="brand-title">
      <!-- Single main H1 for SEO -->
      <h1>Hyper <span>Downloader</span></h1>
    </div>
  </div>

  <!-- Desktop nav -->
  <nav class="nav-desktop">
    <a href="#youtube" class="active"><span class="icon">▶</span><span>YouTube</span></a>
    <a href="#instagram"><span class="icon">📸</span><span>Instagram</span></a>
    <a href="#facebook"><span class="icon">📘</span><span>Facebook</span></a>
    <a href="#twitter"><span class="icon">🐦</span><span>Twitter</span></a>
    <a href="#tiktok"><span class="icon">🎵</span><span>TikTok</span></a>
    <a href="#dailymotion"><span class="icon">📺</span><span>Dailymotion</span></a>
  </nav>

  <!-- Mobile hamburger -->
  <button class="nav-toggle" type="button" aria-label="Toggle navigation">
    <span></span>
  </button>
</header>

<!-- Mobile nav drawer -->
<div class="nav-panel" id="mobileNav">
  <div class="nav-panel-inner">
    <a href="#youtube" class="active"><span class="icon">▶</span><span>YouTube</span></a>
    <a href="#instagram"><span class="icon">📸</span><span>Instagram</span></a>
    <a href="#facebook"><span class="icon">📘</span><span>Facebook</span></a>
    <a href="#twitter"><span class="icon">🐦</span><span>Twitter</span></a>
    <a href="#tiktok"><span class="icon">🎵</span><span>TikTok</span></a>
    <a href="#dailymotion"><span class="icon">📺</span><span>Dailymotion</span></a>
  </div>
</div>

<main class="card" id="top">
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      <!-- Hero line as H2 (H1 already in header) -->
      <h2 style="margin:0;display:flex;flex-wrap:wrap;align-items:center;gap:8px;">
        <span style="color:#FF0000; white-space:nowrap;">YouTube</span>
        <span>&amp;</span>
        <span class="instagram-text" style="white-space:nowrap;">Instagram</span>
        <span style="white-space:nowrap;">Video Downloader</span>
      </h2>
  </div>
  <p class="small">Paste your link, select format, and start. Progress and speed show in real-time. Use it only for content you are allowed to download.</p>

  <div id="preview" class="preview">
    <div class="preview-row">
      <img id="thumb" class="thumb" alt="Video thumbnail preview">
      <div class="meta">
        <div id="pTitle" class="title"></div>
        <div id="pSub" class="sub"></div>
      </div>
    </div>
  </div>

  <form id="frm">
    <div class="grid">
      <div>
        <label>Video URL</label>
        <input id="url" placeholder="https://youtube.com/watch?v=... or any supported link" required>
      </div>

      <div>
        <label>Format</label>
        <select id="format">
          <option value="video">Video (merge bestvideo + bestaudio)</option>
          <option value="audio">Audio only (MP3)</option>
        </select>
      </div>

      <div>
        <label>Video quality</label>
        <select id="video_res">
          <option value="144">144p</option>
          <option value="240">240p</option>
          <option value="360">360p</option>
          <option value="480">480p</option>
          <option value="720">720p</option>
          <option value="1080" selected>1080p</option>
        </select>
      </div>

      <div>
        <label>Audio bitrate (kbps)</label>
        <select id="audio_bitrate">
          <option value="128">128 kbps</option>
          <option value="160">160 kbps</option>
          <option value="192" selected>192 kbps</option>
          <option value="256">256 kbps</option>
          <option value="320">320 kbps</option>
        </select>
      </div>

      <div>
        <label>Filename</label>
        <input id="name" placeholder="My video">
      </div>

      <div class="full">
        <button id="goBtn" type="submit">⚡ Start Download</button>
      </div>
    </div>
  </form>

  <div class="progress">
    <div id="bar" class="bar"></div>
    <div id="pct" class="pct">0%</div>
  </div>

  <div class="status-row" aria-live="polite">
    <div id="msg" class="status-left">—</div>
    <div id="eta" class="eta-pill">
      <span class="label">ETA:</span><span class="value">--</span>
    </div>
  </div>
</main>

<section class="card" id="how-to-use">
  <h2 class="section-title">How to use Hyper Downloader</h2>
  <p class="section-text">Follow these simple steps to download videos and audio from YouTube, Instagram, Facebook, Twitter, TikTok and Dailymotion.</p>

  <div class="howto-grid">
    <div class="howto-item">
      <div class="howto-badge">1</div>
      <h3 style="margin:10px 0 4px;font-size:15px;">Copy the video link</h3>
      <p class="section-text" style="font-size:13px;">Open your favourite platform, copy the video URL from the browser address bar or share menu.</p>
      <div class="howto-illus">
        <img src="/static/s1.png" alt="Start download and watch progress bar">
      </div>
    </div>

    <div class="howto-item">
      <div class="howto-badge">2</div>
      <h3 style="margin:10px 0 4px;font-size:15px;">Paste & choose format</h3>
      <p class="section-text" style="font-size:13px;">Paste the link in the box above, select video or audio, choose quality and bitrate as you like.</p>
      <div class="howto-illus">
        <img src="/static/p2.jpg" alt="Start download and watch progress bar">
      </div>
    </div>

    <div class="howto-item">
      <div class="howto-badge">3</div>
      <h3 style="margin:10px 0 4px;font-size:15px;">Start download</h3>
      <p class="section-text" style="font-size:13px;">Click on <strong>Start Download</strong> and wait. Progress, speed and estimated time will update in real time.</p>
      <div class="howto-illus">
        <img src="/static/p3.jpg" alt="Start download and watch progress bar">
      </div>
    </div>
  </div>
</section>

<section class="card" id="youtube">
  <h2 class="section-title">YouTube Video Downloader</h2>
  <p class="section-text">
    Download YouTube videos in MP4 or convert them to MP3 audio. Support for HD resolutions wherever available, including 720p and 1080p.
  </p>
  <ul class="list">
    <li>Works with standard videos, music videos, tutorials and more.</li>
    <li>Merge best video and best audio into a single high-quality file (when technically possible).</li>
    <li>No software installation required – everything runs in your browser.</li>
  </ul>
</section>

<section class="card" id="instagram">
  <h2 class="section-title">Instagram Video & Reels Downloader</h2>
  <p class="section-text">
    Save Instagram Reels, feed videos and story videos that are publicly accessible. Keep your favourite clips available offline.
  </p>
  <ul class="list">
    <li>Paste any public Instagram video or Reels link.</li>
    <li>Convert to MP4 video or extract MP3 audio.</li>
    <li>Use only for content that you are allowed to download.</li>
  </ul>
</section>

<section class="card" id="facebook">
  <h2 class="section-title">Facebook Video Downloader</h2>
  <p class="section-text">
    Download public Facebook videos quickly. Simply copy the link of any public post and paste it in the box above.
  </p>
  <ul class="list">
    <li>Supports public pages and public profile posts.</li>
    <li>Choose between multiple resolutions when available.</li>
    <li>Please respect the rights of content owners and Facebook policies.</li>
  </ul>
</section>

<section class="card" id="twitter">
  <h2 class="section-title">Twitter / X Video Downloader</h2>
  <p class="section-text">
    Save Twitter (X) videos for offline viewing. Works with public tweets that contain video.
  </p>
  <ul class="list">
    <li>Copy tweet link and paste it in the video URL field.</li>
    <li>Export as MP4 video or MP3 audio.</li>
    <li>Ideal for saving clips, memes and short videos that you are allowed to reuse.</li>
  </ul>
</section>

<section class="card" id="tiktok">
  <h2 class="section-title">TikTok Video Downloader</h2>
  <p class="section-text">
    Download short-form TikTok videos and keep your favourite content offline.
  </p>
  <ul class="list">
    <li>Paste TikTok video links into the downloader.</li>
    <li>Support for different qualities (where available).</li>
    <li>Use only for personal, lawful use and follow TikTok guidelines.</li>
  </ul>
</section>

<section class="card" id="dailymotion">
  <h2 class="section-title">Dailymotion Video Downloader</h2>
  <p class="section-text">
    Download Dailymotion videos and convert them into MP4 or MP3 for easy use on any device.
  </p>
  <ul class="list">
    <li>Copy the Dailymotion video URL and paste it above.</li>
    <li>Choose your preferred resolution and format.</li>
    <li>Fast, secure, and works in most modern browsers.</li>
  </ul>
</section>

<section class="card" id="features">
  <h2 class="section-title">Why use Hyper Downloader?</h2>
  <div class="badge-row">
    <span class="badge">Free to use</span>
    <span class="badge">No signup</span>
    <span class="badge">Fast conversions</span>
    <span class="badge">Multiple platforms</span>
    <span class="badge">HD support</span>
    <span class="badge">Clean UI</span>
  </div>
  <p class="section-text">
    Hyper Downloader is designed to be a simple, fast and safe way to save your favourite online videos. All heavy processing happens on the server side while you get a clear and minimal interface.
  </p>

  <div class="faq-item">
    <div class="faq-q">Is Hyper Downloader free?</div>
    <div class="faq-a">Yes, this tool is free to use. Some limits or fair-use policies may apply to protect the service.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q">Do I need to install any software or extension?</div>
    <div class="faq-a">No installation is required. You only need a modern web browser and a video URL from a supported platform.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q">Can I download private or paid content?</div>
    <div class="faq-a">
      No. Hyper Downloader is intended only for publicly accessible videos and content that you have permission to download.
      Do not use it to download private, paid, DRM-protected or otherwise restricted content.
    </div>
  </div>
</section>

<section class="card" id="privacy">
  <h2 class="section-title">Privacy Policy</h2>
  <p class="section-text">
    We respect your privacy. Hyper Downloader does not require account creation or personal registration to use the basic features.
  </p>
  <ul class="list">
    <li>We may log technical information (such as IP address, browser type and error logs) to keep the service secure and to improve performance.</li>
    <li>Links you submit are processed only for the purpose of generating downloadable media files.</li>
    <li>We do not claim ownership over any content you download. All rights remain with the original content owners.</li>
    <li>Third-party analytics or advertising tools, if used, may set their own cookies and collect usage statistics.</li>
  </ul>
  <p class="section-text" style="margin-top:10px;">
    By using this website, you agree to this Privacy Policy. This page may be updated occasionally; please review it from time to time.
  </p>
</section>

<section class="card" id="terms">
  <h2 class="section-title">Terms of Service</h2>
  <ul class="list">
    <li>You are solely responsible for how you use downloaded content.</li>
    <li>Only download videos that you have the legal right to download (for example, your own content or content under a licence that permits downloading).</li>
    <li>Do not use this website for any illegal activities, including copyright infringement or violation of any platform’s Terms of Service (such as YouTube, Instagram or others).</li>
    <li>The service is provided “as is”, without any warranties of any kind.</li>
    <li>We may change, limit or discontinue the service at any time without notice.</li>
  </ul>
</section>

<section class="card" id="contact">
  <h2 class="section-title">Contact Us</h2>
  <p class="section-text">
    Have questions, feedback or found an issue? You can contact the Hyper Downloader team using the email address below.
  </p>
  <p class="section-text">
    Email: <a href="mailto:support@hyperdownloader.com" style="color:#93c5fd;text-decoration:none;">support@hyperdownloader.com</a><br>
    (Replace this email with your own support address if needed.)
  </p>
</section>

<section class="card" id="disclaimer">
  <h2 class="section-title">Disclaimer & Legal Notice</h2>
  <p class="section-text">
    Hyper Downloader is an independent tool and is not affiliated with, endorsed by, or in any way officially connected to
    YouTube, Instagram, Facebook, Twitter, TikTok, Dailymotion or any of their parent companies.
  </p>
  <p class="section-text">
    All trademarks, service marks, trade names, logos and brands are the property of their respective owners.
    This tool is provided for convenience and educational purposes only. You must always follow the terms of service of each platform
    and comply with local laws and copyright regulations. If you are unsure whether you are allowed to download certain content,
    do not download it.
  </p>
</section>

<footer>
  <div class="footer-links">
    <a href="#top">Home</a>
    <a href="#how-to-use">How to use</a>
    <a href="#features">Features</a>
    <a href="#privacy">Privacy Policy</a>
    <a href="#terms">Terms of Service</a>
    <a href="#contact">Contact</a>
  </div>
  <div>© 2025 Hyper Downloader — Auto cleanup & responsive UI</div>
</footer>
</div>

<script>
let job=null;
const bar=document.getElementById("bar"),pct=document.getElementById("pct");
const msg=document.getElementById("msg");
const etaEl=document.getElementById("eta");
const etaVal=document.querySelector("#eta .value");
const urlIn=document.getElementById("url"),thumb=document.getElementById("thumb"),preview=document.getElementById("preview"),pTitle=document.getElementById("pTitle"),pSub=document.getElementById("pSub");

document.getElementById("frm").addEventListener("submit",async(e)=>{
  e.preventDefault();
  msg.textContent="⏳ Starting...";
  etaVal.textContent="--";
  const url=urlIn.value.trim(),
        fmt=document.getElementById("format").value,
        name=document.getElementById("name").value.trim(),
        video_res=document.getElementById("video_res").value,
        audio_bitrate=document.getElementById("audio_bitrate").value;
  try{
    const r=await fetch("/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,format_choice:fmt,filename:name,video_res,audio_bitrate})});
    const j=await r.json();
    if(!r.ok)throw new Error(j.error||"Failed to start");
    job=j.job_id;poll();
  }catch(err){msg.textContent="❌ "+err.message; etaVal.textContent="--";}
});

urlIn.addEventListener("input",()=>{
  clearTimeout(window._deb);
  const u=urlIn.value.trim();
  if(!/^https?:\/\//i.test(u)){preview.style.display="none";return;}
  window._deb=setTimeout(()=>fetchInfo(u),500);
});
async function fetchInfo(url){
  try{
    const r=await fetch("/info",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});
    const j=await r.json();
    if(!r.ok||j.error){preview.style.display="none";return;}
    pTitle.textContent=j.title||"";pSub.textContent=[j.channel,j.duration_str].filter(Boolean).join(" • ");
    if(j.thumbnail)thumb.src=j.thumbnail;
    preview.style.display="block";
  }catch(e){preview.style.display="none";}
}

function formatSeconds(s){
  if(s===null || s===undefined || !isFinite(s) || s<0) return "--";
  s=Math.round(s);
  const h=Math.floor(s/3600); const m=Math.floor((s%3600)/60); const sec=s%60;
  if(h>0) return `${h}h ${m}m ${sec}s`;
  if(m>0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function formatMbps(speed_b){
  if(!speed_b || speed_b <= 0) return "0.0 Mbps";
  const mbps = (speed_b * 8) / 1000000;
  return mbps.toFixed(1) + " Mbps";
}

async function poll(){
  if(!job)return;
  try{
    const r=await fetch("/progress/"+job);
    if(r.status===404){msg.textContent="Job expired.";etaVal.textContent="--";job=null;return;}
    const p=await r.json();
    const pctv=Math.max(0,Math.min(100,p.percent||0));
    bar.style.width=pctv+"%";pct.textContent=pctv+"%";

    if(p.status==="finished"){msg.textContent="✅ Preparing file...";}
    else if(p.status==="error"){msg.textContent="❌ "+(p.error||"Download failed");}
    else msg.textContent = p.status==="downloaded" ? "✅ Download complete (fetching file)..." : p.status || "Downloading…";

    let etaText="--";
    if(typeof p.eta_seconds !== "undefined" && p.eta_seconds !== null){
      etaText = formatSeconds(p.eta_seconds);
    } else {
      try{
        const downloaded = p.downloaded_bytes || 0;
        const total = p.total_bytes || 0;
        const speed = p.speed_bytes || 0;
        if(total>0 && downloaded>0 && speed>0 && downloaded < total){
          const remain = (total - downloaded)/speed;
          etaText = formatSeconds(remain);
        } else {
          etaText="--";
        }
      }catch(e){etaText="--";}
    }
    etaVal.textContent = etaText;
    etaEl.title = "Speed: " + formatMbps(p.speed_bytes || 0);

    if(p.status==="finished"){ window.location="/fetch/"+job; job=null; return; }
    if(p.status==="error"){ job=null; return; }
    setTimeout(poll,800);
  }catch(e){msg.textContent="Network error.";etaVal.textContent="--";job=null;}
}

/* Navbar highlighting + mobile open/close */
const desktopNavLinks = document.querySelectorAll(".nav-desktop a[href^='#']");
const mobileNav = document.getElementById("mobileNav");
const mobileNavLinks = mobileNav.querySelectorAll("a[href^='#']");
const navLinks = [...desktopNavLinks, ...mobileNavLinks];

const sections = Array.from(navLinks).map(a=>{
  const id = a.getAttribute("href").slice(1);
  const el = document.getElementById(id);
  return el ? {id, el} : null;
}).filter(Boolean);

window.addEventListener("scroll",()=>{
  let currentId = null;
  const scrollY = window.scrollY + 120;
  for(const s of sections){
    const top = s.el.offsetTop;
    if(scrollY >= top) currentId = s.id;
  }
  if(currentId){
    navLinks.forEach(a=>a.classList.remove("active"));
    navLinks.forEach(a=>{
      if(a.getAttribute("href")==="#"+currentId) a.classList.add("active");
    });
  }
});

/* mobile toggle */
const toggleBtn = document.querySelector(".nav-toggle");
toggleBtn.addEventListener("click", ()=>{
  const isOpen = mobileNav.classList.contains("open");
  if(isOpen){
    mobileNav.classList.remove("open");
    toggleBtn.classList.remove("open");
  }else{
    mobileNav.classList.add("open");
    toggleBtn.classList.add("open");
  }
});
mobileNavLinks.forEach(a=>{
  a.addEventListener("click", ()=>{
    mobileNav.classList.remove("open");
    toggleBtn.classList.remove("open");
  });
});
</script>
</body>
</html>
"""

# ---------- Backend objects ----------
JOBS = {}
JOBS_LOCK = threading.Lock()


class Job:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.tmp = Path(tempfile.mkdtemp(prefix="mvd_"))
        self.percent = 0
        self.status = "queued"
        self.file = None
        self.error = None
        self.speed_bytes = 0.0
        self.created_at = time.time()
        self.downloaded_at = None
        self.total_bytes = 0
        self.downloaded_bytes = 0
        JOBS[self.id] = self


URL_RE = re.compile(r"^https?://", re.I)
_FILENAME_SANITIZE_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str, max_len: int = 240) -> str:
    if not name:
        return "file"
    s = name.strip()
    s = _FILENAME_SANITIZE_RE.sub("_", s)
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def _build_video_format(video_res):
    if not video_res:
        return "bestvideo[vcodec!=none]+bestaudio/best"
    try:
        res = int(video_res)
    except Exception:
        res = None
    if not res:
        return "bestvideo[vcodec!=none]+bestaudio/best"
    parts = []
    if res <= 1080:
        parts.append(
            f"bestvideo[height<={res}][vcodec!=none][ext=mp4]+bestaudio/best[height<={res}]"
        )
    parts.append(f"bestvideo[height<={res}][vcodec!=none]+bestaudio")
    parts.append("bestvideo+bestaudio/best")
    return "/".join(parts)


executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)


def _find_output_file(tmpdir: Path, prefix_base: str):
    candidates = list(tmpdir.glob(f"{prefix_base}__*"))
    if not candidates:
        candidates = list(tmpdir.iterdir())
    files = [p for p in candidates if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_size)


def _run_yt_dlp_extract(job: Job, opts: dict, url: str):
    with YoutubeDL(opts) as y:
        y.extract_info(url, download=True)
    return True


def run_download(job: Job, url: str, fmt_key: str, filename: str = None, video_res=None, audio_bitrate=None):
    """Run yt-dlp with ffmpeg-safe fallbacks so it works even when ffmpeg is missing."""
    try:
        if not URL_RE.match(url):
            job.status = "error"
            job.error = "Invalid URL"
            return

        try:
            vres = int(video_res) if video_res else None
        except Exception:
            vres = None
        try:
            abitrate = int(audio_bitrate) if audio_bitrate else None
        except Exception:
            abitrate = None

        # --- Format selection (ffmpeg aware) ---
        if fmt_key == "audio":
            fmt = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            if HAS_FFMPEG:
                fmt = _build_video_format(vres)
            else:
                # No ffmpeg → pick single best stream (no merge)
                fmt = "best[ext=mp4]/best"

        def hook(d):
            try:
                st = d.get("status")
                if st == "downloading":
                    job.status = "downloading"
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0) or 0
                    job.total_bytes = int(total or 0)
                    job.downloaded_bytes = int(downloaded or 0)
                    job.speed_bytes = d.get("speed") or 0
                    if job.total_bytes:
                        job.percent = int(
                            min(
                                100,
                                max(
                                    0,
                                    (job.downloaded_bytes * 100)
                                    / job.total_bytes,
                                ),
                            )
                        )
                elif st == "finished":
                    job.percent = 100
            except Exception:
                pass

        base_template = (filename.strip() if filename else "%(title)s").rstrip(".")
        if "%(" in base_template and ")" in base_template:
            def _replace_outside_tokens(s):
                out = []
                i = 0
                while i < len(s):
                    if s[i] == "%" and i + 1 < len(s) and s[i + 1] == "(":
                        j = i + 2
                        while j < len(s) and s[j] != ")":
                            j += 1
                        if j < len(s):
                            out.append(s[i:j+1])
                            i = j + 1
                            continue
                        else:
                            out.append(s[i:])
                            break
                    else:
                        out.append(s[i])
                        i += 1
                joined = "".join(out)
                return _FILENAME_SANITIZE_RE.sub("_", joined)
            safe_base = _replace_outside_tokens(base_template)
        else:
            safe_base = sanitize_filename(base_template)

        prefix_safe = _FILENAME_SANITIZE_RE.sub("_", APP_PREFIX.strip() or "Hyper_Downloader")
        outtmpl_base = f"{prefix_safe}__{safe_base}"
        outtmpl = str(job.tmp.joinpath(outtmpl_base + ".%(ext)s"))

        opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "quiet": not DEBUG_LOG,
            "no_warnings": True,
            "noplaylist": True,
            "retries": 3,
            "socket_timeout": 30,
            "cookiefile": "cookies.txt",
        }

        if DEBUG_LOG:
            opts["verbose"] = True

        # post-processing / ffmpeg options
        if fmt_key == "audio":
            if HAS_FFMPEG:
                pp = {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
                pp["preferredquality"] = str(abitrate) if abitrate else "192"
                opts["postprocessors"] = [pp]
        else:
            if HAS_FFMPEG:
                opts["ffmpeg_location"] = _FFMPEG
                opts["merge_output_format"] = "mp4"

        try:
            if DEBUG_LOG:
                print(f"[DEBUG] Starting download job {job.id} fmt={fmt} outtmpl={outtmpl} url={url}")
            _run_yt_dlp_extract(job, opts, url)
        except Exception as e:
            job.status = "error"
            job.error = f"yt-dlp failed: {str(e)[:400]}"
            if DEBUG_LOG:
                print(f"[ERROR] job {job.id} yt-dlp exception: {repr(e)}")
            return

        found = _find_output_file(job.tmp, prefix_safe)
        if found:
            job.file = str(found)
            job.status = "finished"
            if DEBUG_LOG:
                print(f"[DEBUG] job {job.id} finished file={job.file}")
        else:
            files = list(job.tmp.glob("*"))
            files = [p for p in files if p.is_file()]
            if files:
                job.file = str(max(files, key=lambda p: p.stat().st_size))
                job.status = "finished"
                if DEBUG_LOG:
                    print(f"[DEBUG] job {job.id} fallback file={job.file}")
            else:
                job.status = "error"
                job.error = "No output file produced"
                if DEBUG_LOG:
                    print(f"[ERROR] job {job.id} - no output file found in {job.tmp}")
    except Exception as e:
        job.status = "error"
        job.error = str(e)[:400]
        if DEBUG_LOG:
            print(f"[ERROR] run_download unexpected: {repr(e)}")


@app.post("/start")
def start():
    d = request.json or {}
    job = Job()
    executor.submit(
        run_download,
        job,
        d.get("url", ""),
        d.get("format_choice", "video"),
        d.get("filename"),
        d.get("video_res"),
        d.get("audio_bitrate"),
    )
    return jsonify({"job_id": job.id})


@app.post("/info")
def info():
    d = request.json or {}
    url = d.get("url", "")
    try:
        with YoutubeDL({"skip_download": True, "quiet": True, "noplaylist": True, "cookiefile": "cookies.txt"}) as y:
            info = y.extract_info(url, download=False)
        title = info.get("title", "")
        channel = info.get("uploader") or info.get("channel", "")
        thumb = info.get("thumbnail")
        dur = info.get("duration") or 0
        return jsonify({"title": title, "thumbnail": thumb, "channel": channel, "duration_str": f"{dur//60}:{dur%60:02d}"})
    except Exception as e:
        if DEBUG_LOG:
            print("[DEBUG] preview failed:", repr(e))
        return jsonify({"error": "Preview failed", "detail": str(e)[:400]}), 400


@app.get("/progress/<id>")
def progress(id):
    j = JOBS.get(id)
    if not j:
        abort(404)
    speed_b = getattr(j, "speed_bytes", 0) or 0
    eta_seconds = None
    downloaded = getattr(j, "downloaded_bytes", 0) or 0
    total = getattr(j, "total_bytes", 0) or 0
    if total > 0 and downloaded > 0 and speed_b and speed_b > 0 and downloaded < total:
        try:
            eta_seconds = int((total - downloaded) / speed_b)
        except Exception:
            eta_seconds = None
    return jsonify({
        "percent": j.percent,
        "status": j.status,
        "error": j.error,
        "speed_bytes": speed_b,
        "downloaded_bytes": downloaded,
        "total_bytes": total,
        "eta_seconds": eta_seconds
    })


@app.get("/fetch/<id>")
def fetch(id):
    j = JOBS.get(id)
    if not j:
        abort(404)
    if not j.file or not os.path.exists(j.file):
        return jsonify({"error": "File not ready"}), 400
    j.downloaded_at = time.time()
    j.status = "downloaded"
    return send_file(j.file, as_attachment=True, download_name=os.path.basename(j.file))


@app.get("/env")
def env():
    return jsonify({
        "ffmpeg": HAS_FFMPEG,
        "ffmpeg_path": _FFMPEG,
        "debug": DEBUG_LOG,
        "prefix": APP_PREFIX,
        "max_concurrent": MAX_CONCURRENT
    })


def cleanup_worker():
    while True:
        try:
            now = time.time()
            remove = []
            for jid, job in list(JOBS.items()):
                if job.status in ("finished", "error") and (now - job.created_at > JOB_TTL_SECONDS):
                    remove.append(jid)
                if job.status == "downloaded" and job.downloaded_at and (now - job.downloaded_at > DOWNLOAD_KEEP_SECONDS):
                    remove.append(jid)
            for rid in remove:
                j = JOBS.pop(rid, None)
                if j:
                    try:
                        shutil.rmtree(str(j.tmp), ignore_errors=True)
                    except Exception:
                        pass
        except Exception as e:
            if DEBUG_LOG:
                print("[cleanup] error:", repr(e))
        time.sleep(CLEANUP_INTERVAL)


threading.Thread(target=cleanup_worker, daemon=True).start()

@app.get("/p1")
def p1():
    return send_file("pages/p1.html")

# ----- SEO ROUTES (SITEMAP + ROBOTS) -----


@app.get("/sitemap.xml")
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://yt-downloader-s52z.onrender.com/</loc>
    <priority>1.0</priority>
    <changefreq>daily</changefreq>
  </url>
</urlset>
"""
    return xml, 200, {"Content-Type": "application/xml"}


@app.get("/robots.txt")
def robots():
    txt = """User-agent: *
Allow: /

Sitemap: https://yt-downloader-s52z.onrender.com/sitemap.xml
"""
    return txt, 200, {"Content-Type": "text/plain"}


@app.get("/")
def home():
    return render_template_string(HTML)


if __name__ == "__main__":
    if DEBUG_LOG:
        print("[INFO] Starting app with config:", {
            "port": PORT, "ffmpeg": HAS_FFMPEG, "ffmpeg_path": _FFMPEG,
            "debug": DEBUG_LOG, "prefix": APP_PREFIX, "max_concurrent": MAX_CONCURRENT
        })
    app.run(host="0.0.0.0", port=PORT)
