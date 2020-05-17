from google.cloud import vision
import io, os, cv2
import time
import re
import sys
import os

import keyboard

import pyaudio
from pygame import mixer 
import json
from google.cloud import automl_v1beta1
from google.cloud.automl_v1beta1.proto import service_pb2
import base64
import requests



import tkinter as tk

from google.cloud import texttospeech
bo=True

from google.cloud import speech_v1 as speech
from google.cloud.speech_v1 import enums
from six.moves import queue
# Audio recording parameters
STREAMING_LIMIT = 10000
SAMPLE_RATE = 16000
CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms
counter=0
def textShow(s):
  root = tk.Tk()
  T = tk.Text(root, height=2, width=30)
  T.pack()
  T.insert(tk.END, s)
  tk.mainloop()
def speakText(sa):
  # Instantiates a client
  client = texttospeech.TextToSpeechClient()

  # Set the text input to be synthesized
  synthesis_input = texttospeech.types.SynthesisInput(text=sa)

  # Build the voice request, select the language code ("en-US") and the ssml
  # voice gender ("neutral")
  voice = texttospeech.types.VoiceSelectionParams(
      language_code='en-US',
      ssml_gender=texttospeech.enums.SsmlVoiceGender.FEMALE)

  # Select the type of audio file you want returned
  audio_config = texttospeech.types.AudioConfig(
      audio_encoding=texttospeech.enums.AudioEncoding.MP3)

  # Perform the text-to-speech request on the text input with the selected
  # voice parameters and audio file type
  response = client.synthesize_speech(synthesis_input, voice, audio_config)

  # The response's audio_content is binary.
  global counter
  with open('%s.mp3'% counter, 'wb') as out:
      # Write the response to the output file.
      out.write(response.audio_content)
  time.sleep(1)
  
  mixer.init()
  mixer.music.load('%s.mp3' %counter)
  keyboard.press_and_release("k+j")
  mixer.music.play()
  time.sleep(5)
  keyboard.press_and_release("k+j") 
  
  
  counter+=1
  

  def get_current_time():
    """Return Current Time in MS."""

    return int(round(time.time() * 1000))

   
def get_prediction(content):
  prediction_client = automl_v1beta1.PredictionServiceClient()
  project_id='144025793143'
  model_id='ICN8431156316856123392' 

  name = 'projects/{}/locations/us-central1/models/{}'.format(project_id, model_id)
  payload = {'image': {'image_bytes': content }}
  params = {}
  request = prediction_client.predict(name, payload, params)
 
  
  xs=str(request)
  if "Happy" in xs:
    speakText("Your pet is happy. You are doing a great job!")
  elif "Sad" in xs:
      speakText("Your pet is not emotionally well. Please take care")
  elif "Anxious" in xs:
      speakText("Your pet is stressed. Please give it some space, or let it go outside.")   

  
 

      
 




class ResumableMicrophoneStream:

    def __init__(self, rate, chunk_size):
        self._rate = rate
        self.chunk_size = chunk_size
        self._num_channels = 1
        self._buff = queue.Queue()
        self.closed = True
        self.start_time = get_current_time()
        self.restart_counter = 0
        self.audio_input = []
        self.last_audio_input = []
        self.result_end_time = 0
        self.is_final_end_time = 0
        self.final_request_end_time = 0
        self.bridging_offset = 0
        self.last_transcript_was_final = False
        self.new_stream = True
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._num_channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self.chunk_size,
         
            stream_callback=self._fill_buffer,
        )

    def __enter__(self):

        self.closed = False
        return self

    def __exit__(self, type, value, traceback):

        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, *args, **kwargs):
        
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        """Stream Audio from microphone to API and to local buffer"""

        while not self.closed:
            data = []

            if self.new_stream and self.last_audio_input:

                chunk_time = STREAMING_LIMIT / len(self.last_audio_input)

                if chunk_time != 0:

                    if self.bridging_offset < 0:
                        self.bridging_offset = 0

                    if self.bridging_offset > self.final_request_end_time:
                        self.bridging_offset = self.final_request_end_time

                    chunks_from_ms = round((self.final_request_end_time -
                                            self.bridging_offset) / chunk_time)

                    self.bridging_offset = (round((
                        len(self.last_audio_input) - chunks_from_ms)
                                                  * chunk_time))

                    for i in range(chunks_from_ms, len(self.last_audio_input)):
                        data.append(self.last_audio_input[i])

                self.new_stream = False

            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            self.audio_input.append(chunk)

            if chunk is None:
                return
            data.append(chunk)
            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)

                    if chunk is None:
                        return
                    data.append(chunk)
                    self.audio_input.append(chunk)

                except queue.Empty:
                    break

            yield b''.join(data)


def listen_print_loop(responses, stream):
    for response in responses:

        if get_current_time() - stream.start_time > STREAMING_LIMIT:
            stream.start_time = get_current_time()
            break

        if not response.results:
            continue

        result = response.results[0]

        if not result.alternatives:
            continue

        transcript = result.alternatives[0].transcript

        result_seconds = 0
        result_nanos = 0
        if result.result_end_time.seconds:
            result_seconds = result.result_end_time.seconds

        if result.result_end_time.nanos:
            result_nanos = result.result_end_time.nanos

        stream.result_end_time = int((result_seconds * 1000)
                                     + (result_nanos / 1000000))
        corrected_time = (stream.result_end_time - stream.bridging_offset
                          + (STREAMING_LIMIT * stream.restart_counter))
      
        if result.is_final:
            sys.stdout.write(str(corrected_time) + ': ' + transcript + '\n')

            processInput(transcript)

            stream.is_final_end_time = stream.result_end_time
            stream.last_transcript_was_final = True

            
            if re.search(r'\b(exit|quit)\b', transcript, re.I):
                sys.stdout.write('Exiting...\n')
                stream.closed = True
                break

        else:
            sys.stdout.write(str(corrected_time) + ': ' + transcript + '\r')
            stream.last_transcript_was_final = False


    
def detect_faces(path):
    """Detects faces in an image."""
    
    client = vision.ImageAnnotatorClient()

    with io.open(path, 'rb') as image_file:
        content = image_file.read()

    image = vision.types.Image(content=content)

    response = client.face_detection(image=image)
    faces = response.face_annotations

 
    likelihood_name = ('UNKNOWN', 'VERY_UNLIKELY', 'UNLIKELY', 'POSSIBLE',
                       'LIKELY', 'VERY_LIKELY')
   
     
    for face in faces:
      if likelihood_name[face.anger_likelihood]=='LIKELY'or likelihood_name[face.anger_likelihood]=='VERY_LIKELY':
        speakText("The person is angry. Try to calm the person")
      elif likelihood_name[face.joy_likelihood]=='LIKELY'or likelihood_name[face.joy_likelihood]=='VERY_LIKELY':
        speakText("The person is happy.")
      elif likelihood_name[face.surprise_likelihood]=='LIKELY'or likelihood_name[face.surprise_likelihood]=='VERY_LIKELY':
        speakText("The person is surprised!")
      elif likelihood_name[face.sorrow_likelihood]=='LIKELY'or likelihood_name[face.sorrow_likelihood]=='VERY_LIKELY':
        speakText("The person is sad. Talk to the person to make them feel better")  
      elif likelihood_name[face.anger_likelihood]=='POSSIBLE'and likelihood_name[face.joy_likelihood]=='UNLIKELY' and likelihood_name[face.sorrow_likelihood]=='UNLIKELY'and likelihood_name[face.surprise_likelihood]=='UNLIKELY':
        speakText("The person is angry. Try to calm the person")
      elif likelihood_name[face.joy_likelihood]=='POSSIBLE'and likelihood_name[face.anger_likelihood]=='UNLIKELY' and likelihood_name[face.sorrow_likelihood]=='UNLIKELY'and likelihood_name[face.surprise_likelihood]=='UNLIKELY':
        speakText("The person is happy")
      elif likelihood_name[face.surprise_likelihood]=='POSSIBLE'and likelihood_name[face.joy_likelihood]=='UNLIKELY' and likelihood_name[face.sorrow_likelihood]=='UNLIKELY'and likelihood_name[face.anger_likelihood]=='UNLIKELY':
        speakText("The person is surprised!")
      elif likelihood_name[face.sorrow_likelihood]=='POSSIBLE'and likelihood_name[face.joy_likelihood]=='UNLIKELY' and likelihood_name[face.anger_likelihood]=='UNLIKELY'and likelihood_name[face.surprise_likelihood]=='UNLIKELY':
        speakText("The person is sad. Talk to the person to make them feel better")    
      elif likelihood_name[face.anger_likelihood]=='UNLIKELY'and likelihood_name[face.joy_likelihood]=='VERY_UNLIKELY' and likelihood_name[face.sorrow_likelihood]=='VERY_UNLIKELY'and likelihood_name[face.surprise_likelihood]=='VERY_UNLIKELY':
        speakText("The person is angry. Try to calm the person")
      elif likelihood_name[face.joy_likelihood]=='UNLIKELY'and likelihood_name[face.anger_likelihood]=='VERY_UNLIKELY' and likelihood_name[face.sorrow_likelihood]=='VERY_UNLIKELY'and likelihood_name[face.surprise_likelihood]=='VERY_UNLIKELY':
        speakText("The person is happy")
      elif likelihood_name[face.surprise_likelihood]=='UNLIKELY'and likelihood_name[face.joy_likelihood]=='VERY_UNLIKELY' and likelihood_name[face.sorrow_likelihood]=='VERY_UNLIKELY'and likelihood_name[face.anger_likelihood]=='VERY_UNLIKELY':
        speakText("The person is surprised")
      elif likelihood_name[face.sorrow_likelihood]=='UNLIKELY'and likelihood_name[face.joy_likelihood]=='VERY_UNLIKELY' and likelihood_name[face.anger_likelihood]=='VERY_UNLIKELY'and likelihood_name[face.surprise_likelihood]=='VERY_UNLIKELY':
        speakText("The person is sad. Talk to the person to make them feel better")   
      else:
          speakText("The person maybe feeling anxious. Talk to the person to make them feel better")  
       

        
    if response.error.message:
        raise Exception(
            '{}\nFor more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'.format(
                response.error.message))


def processInput(transcript):
    parse = transcript.replace(" ","").lower()
    global bo
    if "switchmode" in parse:
      if bo:
          bo=False
          speakText("Pet Mode Enabled")  
      elif not bo:
          bo=True
          speakText("Pet Mode Disabled")   
        
    elif "picture" in parse:
      takePic(bo)
      
def takePic(a):
  cam = cv2.VideoCapture(0)

  cv2.namedWindow("test")

  img_counter = 0


  ret, frame = cam.read()
  if not ret:
    print("failed to grab frame")
         
  cv2.imshow("test", frame)
  
  im=cv2.imwrite(filename='img_name.jpg', img=frame)
  
  im = cv2.imshow("Captured Image", im)
  cv2.waitKey(1650)
  cam.release()
  cv2.destroyAllWindows()
  if a:
   detect_faces("img_name.jpg")
  else:
   with open('img_name.jpg', 'rb') as image_file:
    get_prediction(image_file.read())
     
     
     

     



def main():
    client = speech.SpeechClient()
    config = speech.types.RecognitionConfig(
        encoding=speech.enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code='en-US',
        speech_contexts=[speech.types.SpeechContext(
        phrases=["zoomin","zoomout","takepicture","petEdition","switchmode","picture"])],
        max_alternatives=1)
    streaming_config = speech.types.StreamingRecognitionConfig(
        config=config,
        interim_results=True)

    mic_manager = ResumableMicrophoneStream(SAMPLE_RATE, CHUNK_SIZE)
    print(mic_manager.chunk_size)
   
   

    with mic_manager as stream:

        while not stream.closed:
            sys.stdout.write('\n' + str(
                STREAMING_LIMIT * stream.restart_counter) + ': NEW REQUEST\n')

            stream.audio_input = []
            audio_generator = stream.generator()

            requests = (speech.types.StreamingRecognizeRequest(
                audio_content=content)for content in audio_generator)

            responses = client.streaming_recognize(streaming_config,
                                                   requests)

            # Now, put the transcription responses to use.
            listen_print_loop(responses, stream)

            if stream.result_end_time > 0:
                stream.final_request_end_time = stream.is_final_end_time
            stream.result_end_time = 0
            stream.last_audio_input = []
            stream.last_audio_input = stream.audio_input
            stream.audio_input = []
            stream.restart_counter = stream.restart_counter + 1

            if not stream.last_transcript_was_final:
                sys.stdout.write('\n')
            stream.new_stream = True
            


if __name__ == '__main__':
    main()











