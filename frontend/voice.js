/**
 * voice.js — TTS output + STT voice-command input
 *
 * Exports:
 *   speak(text)          — say something aloud, cancels any current speech
 *   startListening()     — begin continuous voice-command recognition
 *   stopListening()      — stop recognition
 */

const synth = window.speechSynthesis;
let _voice = null;

// Pick a female English voice when available
function _loadVoice() {
  const voices = synth.getVoices();
  _voice =
    voices.find(v => v.lang.startsWith("en") && v.name.toLowerCase().includes("female")) ||
    voices.find(v => v.lang.startsWith("en")) ||
    null;
}
synth.addEventListener("voiceschanged", _loadVoice);
_loadVoice();

export function speak(text) {
  if (!text) return;
  synth.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.voice = _voice;
  utt.rate = 1.05;
  utt.pitch = 1.0;
  synth.speak(utt);
  // Mirror text to the voice-feedback bar
  const el = document.getElementById("voice-text");
  if (el) el.textContent = text;
}

// ── STT ───────────────────────────────────────────────────────────────────────

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

let _recog = null;
let _listening = false;

export function startListening() {
  if (!SpeechRecognition) {
    console.warn("SpeechRecognition not supported in this browser.");
    return;
  }
  if (_listening) return;

  _recog = new SpeechRecognition();
  _recog.continuous = true;
  _recog.interimResults = false;
  _recog.lang = "en-IN";

  _recog.onresult = (event) => {
    const transcript = event.results[event.results.length - 1][0].transcript
      .trim()
      .toLowerCase();
    console.log("[STT]", transcript);
    _handleVoiceCommand(transcript);
  };

  _recog.onerror = (e) => {
    if (e.error !== "no-speech") console.warn("[STT error]", e.error);
  };

  _recog.onend = () => {
    // Auto-restart so listening stays continuous
    if (_listening) _recog.start();
  };

  _listening = true;
  _recog.start();
  speak("Listening for commands.");
}

export function stopListening() {
  _listening = false;
  _recog && _recog.stop();
}

// ── Command parser ────────────────────────────────────────────────────────────

function _handleVoiceCommand(text) {
  // Navigation mode
  if (text.includes("navigation mode") || text.includes("navigate mode")) {
    window.setMode("navigation");
    return;
  }
  if (text.includes("shopping mode") || text.includes("shop mode")) {
    window.setMode("shopping");
    return;
  }
  if (text.includes("describe mode") || text.includes("description mode") ||
      text.includes("describe surroundings")) {
    window.setMode("describe");
    return;
  }

  // Navigation commands
  if (text.startsWith("navigate to ") || text.startsWith("go to ") ||
      text.startsWith("take me to ")) {
    const dest = text.replace(/^(navigate to|go to|take me to)\s+/, "");
    window.navigateTo(dest);
    return;
  }

  // POI search
  const poiMatch = text.match(
    /find (?:a |the |nearest )?(hospital|clinic|pharmacy|supermarket|grocery|dentist|barber|police)/
  );
  if (poiMatch) {
    window.findPOI(poiMatch[1]);
    return;
  }

  // Shopping — pick item
  const pickMatch = text.match(/(?:pick|i want|grab|get me)(?: the| a| an)? (.+)/);
  if (pickMatch) {
    window.sendCommand("pick:" + pickMatch[1].trim());
    return;
  }

  // Shopping — done / next / cancel
  if (text === "done" || text === "next item" || text === "next" || text === "cancel") {
    window.sendCommand("done");
    return;
  }

  // Shopping — read list
  if (text.includes("read my list") || text.includes("what's on my list") ||
      text.includes("shopping list")) {
    window.sendCommand("list");
    return;
  }

  // Emergency
  if (text.includes("emergency") || text.includes("help me") || text.includes("s o s")) {
    window.triggerSOS();
    return;
  }
}

// ── SSE scene description renderer ───────────────────────────────────────────

export async function streamDescription(objects) {
  let fullText = "";
  synth.cancel();

  let res;
  try {
    res = await fetch("/describe/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objects }),
    });
  } catch (e) {
    speak("Cannot reach the server. Is the app running?");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") {
        if (fullText) speak(fullText);
        return;
      }
      try {
        const { token } = JSON.parse(payload);
        fullText += token;
      } catch (_) {}
    }
  }

  if (fullText) speak(fullText);
  else speak("No description received. Make sure Ollama is running with: ollama serve");
}
