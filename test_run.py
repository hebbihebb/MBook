import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock torch if not present to allow logic testing in non-GPU/minimal envs
try:
    import torch
except ImportError:
    torch = MagicMock()
    sys.modules['torch'] = torch
    # Mock hub specifically
    torch.hub = MagicMock()

# Mock num2words
try:
    import num2words
except ImportError:
    num2words = MagicMock()
    # Simple mock behavior: return input as string (wrapped)
    num2words.num2words = lambda x: f"word_{x}"
    sys.modules['num2words'] = num2words

# Mock spacy
try:
    import spacy
except ImportError:
    spacy = MagicMock()
    
    # Mocking nlp(text) -> doc -> .sents
    class MockDoc:
        def __init__(self, text):
            self.text = text
            # Simple sentence split by period for testing
            raw_sents = text.replace("Dr.", "Dr").split('.') # Crude split avoiding Dr.
            self.sents = [MockSent(s.strip() + ".") for s in raw_sents if s.strip()]

    class MockSent:
        def __init__(self, text):
            self.text = text
            
    def mock_load(name):
        def nlp(text):
            return MockDoc(text)
        return nlp
        
    spacy.load = mock_load
    sys.modules['spacy'] = spacy

from pipeline import clean_text, chunk_text, validate_audio, Maya1Pipeline
import os

class TestMaya1Pipeline(unittest.TestCase):
    
    def test_clean_text(self):
        print("\nTesting 'clean_text'...")
        input_text = "Dr. Smith was born in 1990.\nHe likes it."
        # Note: num2words mocked to return 'word_X', but 'clean_text' removes underscores!
        # So 'word_1990' -> 'word1990'
        expected_sample_parts = ["Doctor", "word1990"]
        cleaned = clean_text(input_text)
        print(f"Original: {input_text}\nCleaned: {cleaned}")
        
        for part in expected_sample_parts:
            self.assertIn(part, cleaned)
        self.assertNotIn("\n", cleaned) # Newlines should be spaces

    def test_chunk_text(self):
        print("\nTesting 'chunk_text'...")
        # Create a long text
        long_text = "This is a sentence. " * 30
        chunks = chunk_text(long_text, max_words=25)
        print(f"Generated {len(chunks)} chunks.")
        
        for i, chunk in enumerate(chunks[:3]):
            print(f"Chunk {i}: {chunk}")
            self.assertTrue(chunk.startswith("... "))
            self.assertTrue(chunk.endswith(" ..."))
            
    @patch('pipeline.torch.hub.load')
    def test_validation_logic(self, mock_hub_load):
        print("\nTesting 'validate_audio' logic...")
        
        # Mock VAD to return full range (no silence) for simplicity or specific range
        # Mocking the utils tuple return
        mock_get_speech_timestamps = MagicMock(return_value=[{'start': 0, 'end': 24000}])
        mock_utils = (mock_get_speech_timestamps, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_hub_load.return_value = (MagicMock(), mock_utils)
        
        # Configure dummy audio mock to behave like a tensor
        dummy_audio = MagicMock()
        dummy_audio.dim.return_value = 2
        dummy_audio.squeeze.return_value = dummy_audio
        dummy_audio.unsqueeze.return_value = dummy_audio # Fix: Propagate mock
        # Slicing returns itself (simplified)
        dummy_audio.__getitem__.return_value = dummy_audio
        # Shape[-1] returns 24000 (1 sec)
        shape_mock = MagicMock()
        shape_mock.__getitem__.return_value = 24000
        dummy_audio.shape = shape_mock
        
        is_valid, trimmed = validate_audio(dummy_audio, text_char_count=15) # 15 chars ~ 1 sec
        self.assertTrue(is_valid, "Should be valid for perfect match")
        
        # Case: Too long (Hallucination)
        # Configure shape to be 48000 (2 sec)
        dummy_audio_long = MagicMock()
        dummy_audio_long.dim.return_value = 2
        dummy_audio_long.squeeze.return_value = dummy_audio_long
        dummy_audio_long.unsqueeze.return_value = dummy_audio_long # Fix: Propagate mock
        dummy_audio_long.__getitem__.return_value = dummy_audio_long
        
        shape_mock_long = MagicMock()
        shape_mock_long.__getitem__.return_value = 48000
        dummy_audio_long.shape = shape_mock_long
        
        # Note: applying VAD mock again
        mock_get_speech_timestamps.return_value = [{'start': 0, 'end': 48000}]
        
        is_valid_long, _ = validate_audio(dummy_audio_long, text_char_count=15)
        self.assertFalse(is_valid_long, "Should fail length check")

    def test_pipeline_integration_mock(self):
        print("\nTesting Full Pipeline Integration (Mocked Model)...")
        pipeline = Maya1Pipeline()
        # Mock the model and tokenizer to avoid loading
        pipeline.model = MagicMock()
        pipeline.tokenizer = MagicMock()
        
        # Tokenizer needs to return an object with .to()
        mock_inputs = MagicMock()
        mock_inputs.to.return_value = mock_inputs
        pipeline.tokenizer.return_value = mock_inputs
        
        # Mock generate return: random tensor simulating audio
        # Can be anything since we don't validate it strictly here, just flow
        pipeline.model.generate.return_value = MagicMock()
        
        text = "This is a test run."
        cleaned = clean_text(text)
        chunks = chunk_text(cleaned)
        
        generated_chunk = pipeline.generate_chunk(chunks[0], "ref.wav")
        self.assertIsNotNone(generated_chunk)
        print("Integration test passed.")

if __name__ == '__main__':
    unittest.main()
