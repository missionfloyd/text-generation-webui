import random
import time
from pathlib import Path

import gradio as gr
import edge_tts
import asyncio
from modules import chat, shared

from extensions.edge_tts import tts_preprocessor

params = {
    'activate': True,
    'voice': 'en-US-JennyNeural',
    'show_text': False,
    'autoplay': True,
    'rate': '+0%',
    'local_cache_path': ''  # User can override the default cache path to something other via settings.json
}

current_params = params.copy()
voices = [i["ShortName"] for i in asyncio.run(edge_tts.list_voices())]
voice_speeds = {
    'x-slow': "-50%",
    'slow': "-25%",
    'medium': "+0%",
    'fast': "+25%",
    'x-fast': "+50%"
}


def remove_tts_from_history():
    for i, entry in enumerate(shared.history['internal']):
        shared.history['visible'][i] = [shared.history['visible'][i][0], entry[1]]


def toggle_text_in_history():
    for i, entry in enumerate(shared.history['visible']):
        visible_reply = entry[1]
        if visible_reply.startswith('<audio'):
            if params['show_text']:
                reply = shared.history['internal'][i][1]
                shared.history['visible'][i] = [shared.history['visible'][i][0], f"{visible_reply.split('</audio>')[0]}</audio>\n\n{reply}"]
            else:
                shared.history['visible'][i] = [shared.history['visible'][i][0], f"{visible_reply.split('</audio>')[0]}</audio>"]


def state_modifier(state):
    if not params['activate']:
        return state

    state['stream'] = False
    return state


def input_modifier(string):
    if not params['activate']:
        return string

    shared.processing_message = "*Is recording a voice message...*"
    return string


def history_modifier(history):
    # Remove autoplay from the last reply
    if len(history['internal']) > 0:
        history['visible'][-1] = [
            history['visible'][-1][0],
            history['visible'][-1][1].replace('controls autoplay>', 'controls>')
        ]

    return history


def output_modifier(string):
    global current_params, streaming_state

    for i in params:
        if params[i] != current_params[i]:
            current_params = params.copy()
            break

    if not params['activate']:
        return string

    original_string = string
    string = tts_preprocessor.preprocess(string)

    if string == '':
        string = '*Empty reply, try regenerating*'
    else:
        output_file = Path(f'extensions/edge_tts/outputs/{shared.character}_{int(time.time())}.mp3')
        
        communicate = edge_tts.Communicate(string, params['voice'], rate=params["rate"])
        asyncio.run(communicate.save(str(output_file)))
        autoplay = 'autoplay' if params['autoplay'] else ''
        string = f'<audio src="file/{output_file.as_posix()}" controls {autoplay}></audio>'
        if params['show_text']:
            string += f'\n\n{original_string}'

    shared.processing_message = "*Is typing...*"
    return string


async def voice_preview(preview_text):
    global current_params, streaming_state

    for i in params:
        if params[i] != current_params[i]:
            current_params = params.copy()
            break

    if not preview_text:
        with open("extensions/edge_tts/harvard_sentences.txt") as f:
            preview_text = random.choice(list(f))

    string = tts_preprocessor.preprocess(preview_text)

    output_file = Path('extensions/edge_tts/outputs/voice_preview.wav')
    communicate = edge_tts.Communicate(string, params['voice'], rate=params["rate"])
    await communicate.save(str(output_file))

    return f'<audio src="file/{output_file.as_posix()}?{int(time.time())}" controls autoplay></audio>'


def ui():
    # Gradio elements
    with gr.Accordion("Edge TTS"):
        with gr.Row():
            activate = gr.Checkbox(value=params['activate'], label='Activate TTS')
            autoplay = gr.Checkbox(value=params['autoplay'], label='Play TTS automatically')

        show_text = gr.Checkbox(value=params['show_text'], label='Show message text under audio player')
        with gr.Row():
            voice = gr.Dropdown(value=params['voice'], choices=sorted(voices), label='TTS voice')
            v_speed = gr.Dropdown(value="medium", choices=voice_speeds.keys(), label='Voice speed')

        with gr.Row():
            convert = gr.Button('Permanently replace audios with the message texts')
            convert_cancel = gr.Button('Cancel', visible=False)
            convert_confirm = gr.Button('Confirm (cannot be undone)', variant="stop", visible=False)

        with gr.Row():
            preview_text = gr.Text(show_label=False, placeholder="Preview text", elem_id="edge_preview_text")
            preview_play = gr.Button("Preview")
            preview_audio = gr.HTML(visible=False)

    # Convert history with confirmation
    convert_arr = [convert_confirm, convert, convert_cancel]
    convert.click(lambda: [gr.update(visible=True), gr.update(visible=False), gr.update(visible=True)], None, convert_arr)
    convert_confirm.click(
        lambda: [gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)], None, convert_arr).then(
        remove_tts_from_history, None, None).then(
        chat.save_history, shared.gradio['mode'], None, show_progress=False).then(
        chat.redraw_html, shared.reload_inputs, shared.gradio['display'])

    convert_cancel.click(lambda: [gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)], None, convert_arr)

    # Toggle message text in history
    show_text.change(
        lambda x: params.update({"show_text": x}), show_text, None).then(
        toggle_text_in_history, None, None).then(
        chat.save_history, shared.gradio['mode'], None, show_progress=False).then(
        chat.redraw_html, shared.reload_inputs, shared.gradio['display'])

    # Event functions to update the parameters in the backend
    activate.change(lambda x: params.update({"activate": x}), activate, None)
    autoplay.change(lambda x: params.update({"autoplay": x}), autoplay, None)
    voice.change(lambda x: params.update({"voice": x}), voice, None)
    v_speed.change(lambda x: params.update({"rate": voice_speeds[x]}), v_speed, None)

    # Play preview
    preview_text.submit(voice_preview, preview_text, preview_audio)
    preview_play.click(voice_preview, preview_text, preview_audio)
