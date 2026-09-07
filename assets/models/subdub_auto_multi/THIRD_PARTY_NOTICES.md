# Third-party notices — SubDub Auto Multi speaker embedding

## WeSpeaker source

- Project: WeSpeaker, https://github.com/wenet-e2e/wespeaker
- License: Apache License 2.0; see `WESPEAKER.LICENSE.APACHE-2.0`.

## VoxCeleb ResNet34 pretrained runtime model

- Upstream file: `voxceleb_resnet34.onnx`
- Upstream catalog: WeSpeaker `docs/pretrained.md`
- Dataset/model license: Creative Commons Attribution 4.0 International;
  see `VOXCELEB.MODEL.LICENSE.CC-BY-4.0`.
- Model bytes: 26,534,127
- SHA-256: `9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1`
- This repository does not modify the pretrained weight tensor values.

## Syntropic Signal gender voice classifier

- Project: `syntropicsignal-ai/gender-voice-classifier` on Hugging Face.
- Upstream revision: `248c107` (`Initial release: model + card`).
- Upstream file: `gender_classifier_200k.onnx`.
- License declared by the model repository: MIT; see
  `GENDER_CLASSIFIER.MODEL.LICENSE.MIT`.
- Model bytes: 670,311.
- SHA-256: `e98f8bc6d7960a8a2169368fe4533636903e712790e96dbff81b679ede5de252`.
- Input contract: normalized 40-coefficient MFCC from a 3-second, 16 kHz
  mono speech clip; output is one female logit.
- Published scope is English, German, French, Spanish and Italian speech.
  Auto Multi treats this model as bounded register-routing evidence and fails
  closed when its gender partition is not stable; it is not a personal-identity
  claim.
