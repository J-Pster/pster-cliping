"""Etapa 5: reenquadramento vertical 9:16 seguindo o rosto de quem fala."""

from clipador.reframe.crop import CropWindowCalculator
from clipador.reframe.faces import FaceDetector, MediaPipeFaceDetector, faces_from_mediapipe
from clipador.reframe.frames import FrameSampler, OpenCvFrameSampler
from clipador.reframe.models import CropWindow, FaceBox, ReframeError, Scene
from clipador.reframe.reframer import (
    CropKeyframe,
    ReframePlan,
    ReframeResult,
    VerticalReframer,
    build_crop_filter,
)
from clipador.reframe.scenes import (
    PySceneDetector,
    SceneDetector,
    build_scenes,
    sample_frame_indices,
    sample_times,
)
from clipador.reframe.speaker import (
    ActiveSpeakerDetector,
    LargestFaceHeuristic,
    LRASDActiveSpeakerDetector,
    SpeakerContext,
    crop_face_patch,
    extract_mfcc_window,
)

__all__ = [
    "ActiveSpeakerDetector",
    "CropKeyframe",
    "CropWindow",
    "CropWindowCalculator",
    "FaceBox",
    "FaceDetector",
    "FrameSampler",
    "LRASDActiveSpeakerDetector",
    "LargestFaceHeuristic",
    "MediaPipeFaceDetector",
    "OpenCvFrameSampler",
    "PySceneDetector",
    "ReframeError",
    "ReframePlan",
    "ReframeResult",
    "Scene",
    "SceneDetector",
    "SpeakerContext",
    "VerticalReframer",
    "build_crop_filter",
    "build_scenes",
    "crop_face_patch",
    "extract_mfcc_window",
    "faces_from_mediapipe",
    "sample_frame_indices",
    "sample_times",
]
