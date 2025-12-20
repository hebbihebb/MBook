# MBook - TODO & Known Issues

**Last Updated:** 2025-12-20
**Status:** Under Investigation - Critical Issues Confirmed

---

## 🔴 CRITICAL ISSUES - Must Fix Before Production

### Data Corruption & Loss

**CRITICAL #1: Silent Content Loss in Audiobooks**
- **File:** `main.py`
- **Problem:** If chunk generation fails, the error is logged, but the conversion continues.
- **Impact:** Creates corrupted audiobooks with missing chunks (silent gaps).
- **User discovers:** Hours later during playback.
- **Fix Required:**
  - Add validation after stitching to verify all chunks are present.
  - Abort conversion if any chunks are missing.
  - Display a clear error to the user.

**CRITICAL #2: Resume with Different Voice = Mixed Narration**
- **File:** `main.py`
- **Problem:** Resuming a conversion with a different voice prompt uses the old chunks (previous voice) and new chunks (current voice).
- **Impact:** The resulting audiobook has multiple narrators mid-book.
- **Fix Required:** Validate that the voice prompt matches on resume, or force the user to keep the same voice.

**CRITICAL #3: Resume with Different Chapter Selection = Corrupted Book**
- **File:** `main.py`
- **Problem:** The application does not validate if the selected chapters for a resumed conversion match the saved progress.
- **Impact:** The audiobook has the wrong content (missing chapters, duplicates, wrong order).
- **Fix Required:** Store and validate the chapter selection on resume.

**CRITICAL #4: Cancel During Final Processing = UI Lock**
- **File:** `main.py`
- **Problem:** The cancellation event is not checked during the final stitching and M4B export process.
- **Impact:** The UI remains locked, and the user cannot cancel the process for a significant amount of time (potentially 12+ hours of work).
- **Fix Required:** Disable the cancel button during the final processing stage or implement a mechanism to gracefully handle cancellation.

### Security Issues

**CRITICAL #5: Prompt Injection via Quote Escape**
- **File:** `convert_epub_to_audiobook.py`
- **Problem:** The voice description is not escaped, allowing quotes to break the XML/prompt structure.
- **Fix Required:** Escape the description (e.g., `description.replace('"', '&quot;')`) or validate that it contains no special characters.

**CRITICAL #6: Arbitrary Code Execution via Model Loading**
- **Files:** `convert_epub_to_audiobook.py`, `fast_maya_engine.py`
- **Problem:** The use of `trust_remote_code=True` allows for arbitrary code execution from HuggingFace when loading models.
- **Fix Required:**
  - Pin the exact model versions with hash verification.
  - Download models locally and disable internet access during loading.
  - Consider sandboxing the model loading process.

**CRITICAL #7: Path Traversal in EPUB Extraction (Needs Investigation)**
- **File:** `epub_parser.py`
- **Problem:** ZIP entries may not be validated, potentially allowing for path traversal attacks (e.g., `../../../etc/passwd`).
- **Impact:** File overwrite and information disclosure.
- **Fix Required:** Validate that the extracted paths are within a safe directory. Further investigation is needed to confirm the vulnerability in the `ebooklib` library.

**CRITICAL #8: ZIP Bomb / Decompression Bomb**
- **File:** `main.py`
- **Problem:** The application only checks the compressed size of the EPUB file, not the decompressed size.
- **Impact:** A decompression bomb could lead to memory exhaustion and a system crash.
- **Fix Required:** Monitor the decompressed size during extraction and enforce a limit.

**CRITICAL #9: Metadata Sanitization Logic Bug**
- **File:** `assembler.py`
- **Problem:** The sanitization logic has been partially fixed (using a single regex), but it still allows for a Unicode bypass (e.g., U+2028 line separator is not filtered).
- **Fix Required:** Improve the regex to remove all dangerous characters, including Unicode line separators and other control characters.

---

## 🟠 HIGH PRIORITY ISSUES

### User Experience Bugs

**HIGH #1: Cannot Cancel During Model Loading (2-5 min hang)**
- **File:** [main.py:719-746](main.py#L719-L746)
- **Problem:** No cancel check during model loading
- **Impact:** User forced to wait or kill app
- **Fix:** Add cancel check before/during loading, or show "Cannot cancel" message

**HIGH #2: Pause Button Misleading**
- **File:** [main.py:628-632, 814-815](main.py#L814-L815)
- **Problem:** Pause check happens AFTER chunk generation starts
- **Impact:** 1-3 minute delay before actual pause
- **Fix:** Check pause BEFORE starting next chunk

**HIGH #3: Progress Bar Freezes at 85%**
- **File:** [main.py:800-803, 854-895](main.py#L854-L895)
- **Problem:** No progress updates during stitching/M4B export (10-20 min)
- **Impact:** User thinks app is frozen
- **Fix:** Add progress updates every 30 seconds during post-processing

### Performance & Resource Issues

**HIGH #4: Unbounded GPU Memory Allocation**
- **File:** [convert_epub_to_audiobook.py:234-235](convert_epub_to_audiobook.py#L234-L235)
- **Problem:** No upper bound on max_new_tokens
- **Impact:** GPU OOM crash
- **Fix:** `max_new_tokens = min(max_new_tokens, 50000)`

**HIGH #5: Infinite Loop in Text Chunking**
- **File:** [convert_epub_to_audiobook.py:365-481](convert_epub_to_audiobook.py#L365-L481)
- **Problem:** No limit on number of chunks
- **Impact:** 1M chunks = days of processing
- **Fix:** Add MAX_CHUNKS_PER_CONVERSION = 10000

**HIGH #6: EPUB Content Loaded Entirely in Memory**
- **File:** [epub_parser.py:174-177](epub_parser.py#L174-L177)
- **Problem:** All chapters loaded at once (no streaming)
- **Impact:** Large EPUBs cause memory exhaustion
- **Fix:** Implement streaming parser

**HIGH #7: Predictable Temp File Paths (Symlink Attack)**
- **File:** [main.py:665-666, 784](main.py#L665-L666)
- **Problem:** temp_chunks directory has predictable name
- **Impact:** Symlink attacks on multi-user systems
- **Fix:** Use `tempfile.mkdtemp()`, check for symlinks before writing

**HIGH #8: No Symlink Following Check**
- **File:** [main.py:784, 830](main.py#L830)
- **Problem:** soundfile follows symlinks by default
- **Impact:** File overwrite outside intended directory
- **Fix:** Check `os.path.islink()` before writing

### Validation & Error Handling

**HIGH #9: Progress File World-Readable**
- **File:** [progress_manager.py:61-62](progress_manager.py#L61-L62)
- **Problem:** Default 644 permissions expose file paths
- **Fix:** Create with 600 permissions

**HIGH #10: No Validation of Chunk Index from JSON**
- **File:** [progress_manager.py:86-88](progress_manager.py#L86-L88)
- **Problem:** Accepts negative or huge indices
- **Fix:** Validate 0 <= idx <= 100000

**HIGH #11: Command Injection in FFmpeg (Residual Risk)**
- **File:** [assembler.py:46, 234-244](assembler.py#L234-L244)
- **Problem:** Unicode line separators bypass sanitization
- **Fix:** Use whitelist approach, filter all Unicode control chars

**HIGH #12: Signal Handler Doesn't Cleanup**
- **File:** [convert_epub_to_audiobook.py:615-616](convert_epub_to_audiobook.py#L615-L616)
- **Problem:** sys.exit(1) doesn't call cleanup()
- **Fix:** Use atexit.register() or call cleanup explicitly

---

## 🟡 MEDIUM PRIORITY ISSUES

### Content Quality

**MEDIUM #1: Numbers Become Word Salad**
- **File:** [convert_epub_to_audiobook.py:338](convert_epub_to_audiobook.py#L338)
- **Problem:** ALL numbers converted to words (years, phone numbers, addresses)
- **Impact:** Unnatural narration ("two thousand twenty-four", "five hundred fifty-five minus...")
- **Fix:** Make configurable or add context awareness

### User Interface

**MEDIUM #2: No Warning Before Overwriting Audiobook**
- **File:** [assembler.py:297-298](assembler.py#L297-L298)
- **Problem:** Silently overwrites existing M4B files
- **Fix:** Check if file exists, prompt user

**MEDIUM #3: Text Preview Too Short**
- **File:** [main.py:489-496](main.py#L489-L496)
- **Problem:** Only shows 500 characters (~2 sentences)
- **Fix:** Increase to 2000-3000 characters, add scrollbar

**MEDIUM #4: Voice Settings Validation Confusing**
- **File:** [main.py:103-111](main.py#L103-L111)
- **Problem:** No character counter in dialog
- **Fix:** Add live character counter (e.g., "750/1000")

**MEDIUM #5: Elapsed Time Includes Pause Time**
- **File:** [main.py:957-974](main.py#L957-L974)
- **Problem:** Time tracking includes paused duration
- **Fix:** Pause/resume the timer with pause events

**MEDIUM #6: Log Output Scrolls Away Critical Errors**
- **File:** [main.py:350](main.py#L350)
- **Problem:** Only 6 lines visible, errors disappear
- **Fix:** Increase to 20 lines, add search/filter

**MEDIUM #7: Cleanup Failures Fill Up Disk Silently**
- **File:** [main.py:910-926](main.py#L910-L926)
- **Problem:** Temp file cleanup failures not surfaced to user
- **Fix:** Show prominent warning if cleanup fails

**MEDIUM #8: File Size Limit Arbitrary**
- **File:** [main.py:381-386](main.py#L381-L386)
- **Problem:** 500MB limit rejects legitimate anthologies
- **Fix:** Remove or increase to 2GB, warn instead of block

### Security & Dependencies

**MEDIUM #9: Cover Image Loaded Without Validation**
- **File:** [main.py:442-444](main.py#L442-L444)
- **Problem:** PIL has had buffer overflow CVEs
- **Fix:** Validate image size/format before processing

**MEDIUM #10: BeautifulSoup Without XXE Protection**
- **File:** [epub_parser.py:36](epub_parser.py#L36)
- **Problem:** XML External Entity attacks possible
- **Fix:** Use lxml parser with `resolve_entities=False, no_network=True`

**MEDIUM #11: No FFmpeg Version Verification**
- **File:** [assembler.py:9-23](assembler.py#L9-L23)
- **Problem:** Only checks if ffmpeg exists, not version
- **Fix:** Check version >= 4.0

**MEDIUM #12: Batch Size Not Validated Against GPU Memory**
- **File:** [main.py:727-732](main.py#L727-L732)
- **Problem:** Arbitrary limit (64) doesn't consider actual GPU memory
- **Fix:** Calculate based on `torch.cuda.get_device_properties()`

**MEDIUM #13: No Rate Limiting on Conversions**
- **Problem:** Multiple instances can run simultaneously → GPU OOM
- **Fix:** Use file lock to allow only one conversion at a time

**MEDIUM #14: Error Messages Reveal Full Paths**
- **File:** [main.py:432](main.py#L432)
- **Problem:** Exceptions may contain sensitive system paths
- **Fix:** Sanitize error messages (replace home dir with ~)

---

## 🔵 LOW PRIORITY / TECHNICAL DEBT

### Code Quality

1. **Inconsistent Error Handling Patterns**
   - Files use mix of print(), logger.error(), self.log()
   - Fix: Standardize on logging module

2. **Awkward Batch Size Validation Logic**
   - [main.py:726-732](main.py#L726-L732) - nested if statements
   - Fix: Flatten control flow

3. **Broad Exception Catching**
   - [pipeline.py:36](pipeline.py#L36) - catches all Exception
   - Fix: Catch specific exception types

4. **Missing Voice Description Validation at Engine Layer**
   - [convert_epub_to_audiobook.py:197](convert_epub_to_audiobook.py#L197)
   - Only validated in GUI, CLI/API bypass checks
   - Fix: Add validation in generate_audio()

5. **Chapter Title Command Injection (Escaping Bug)**
   - [assembler.py:176-178](assembler.py#L176-L178)
   - Backslash escaped last instead of first
   - Fix: Escape backslash FIRST

6. **No Timeout on Model Loading**
   - [convert_epub_to_audiobook.py:139-155](convert_epub_to_audiobook.py#L139-L155)
   - Network issues → indefinite hang
   - Fix: socket.setdefaulttimeout(300)

7. **Temp Files Use Default Permissions**
   - Multiple files create temp files with 644 (world-readable)
   - Fix: Use 600 permissions

8. **Integer Overflow in Progress Calculation**
   - [main.py:801, 845](main.py#L801)
   - total_chunks = 0 causes ZeroDivisionError
   - Fix: Check for zero before division

9. **Race Condition in Progress File (TOCTOU)**
   - [main.py:553-570](main.py#L553-L570)
   - Time-of-check vs time-of-use gap
   - Fix: Load progress once and reuse

10. **Chapter Order Not Validated**
    - [main.py:469, 401](main.py#L401)
    - Malicious EPUB could have negative or huge order values
    - Fix: Validate 0 <= order < 10000

### Architecture

11. **Code Duplication**
    - SNAC token constants duplicated across files
    - SNAC unpacking logic duplicated (200+ lines)
    - Text cleaning logic duplicated
    - Fix: Extract to shared utility modules

12. **Monster Method (278 lines)**
    - [main.py:608-886](main.py#L608-L886) - run_conversion()
    - Fix: Split into 6-8 separate methods

13. **Hardcoded Configuration**
    - Window dimensions, model paths, chunk parameters, silence duration, etc.
    - Fix: Create config.py or use environment variables

14. **Poor Separation of Concerns**
    - GUI mixed with business logic
    - Fix: Extract to ConversionService class

### Testing

15. **No Unit Tests**
    - Missing tests for: epub_parser, clean_text, chunk_text, progress manager
    - No error handling tests
    - No integration tests

16. **No Security Test Suite**
    - Need tests for: ZIP bombs, path traversal, XXE injection, malicious images
    - Need injection tests: quote injection, control tokens, metadata injection

---

## 📋 IMPLEMENTATION PRIORITY

### Week 1: Critical Data Corruption (MUST FIX)
1. Fix silent content loss (add validation after stitching)
2. Fix resource cleanup safety gaps (per-resource try-except)
3. Validate voice prompt on resume
4. Validate chapter selection on resume
5. Handle cancel during final processing

**Effort:** ~16 hours

### Week 2: Critical Security (MUST FIX)
6. Fix prompt injection via quote escape
7. Add path traversal validation for EPUB extraction
8. Add decompression bomb protection
9. Fix metadata sanitization (Unicode bypass)
10. Use secure temp directories (mkdtemp)
11. Add symlink checks before file writes

**Effort:** ~12 hours

### Week 3: High Priority UX & Performance
12. Fix cannot cancel during model loading
13. Fix pause button delay
14. Add progress updates during post-processing
15. Cap max_new_tokens (GPU OOM protection)
16. Add chunk count limit
17. Fix progress file permissions

**Effort:** ~10 hours

### Week 4: Medium Priority Polish
18. Make number conversion configurable
19. Add overwrite warning
20. Increase text preview size
21. Add character counter to voice dialog
22. Fix elapsed time calculation
23. Increase log window size
24. Surface cleanup failures

**Effort:** ~8 hours

### Month 2+: Technical Debt & Testing
- Refactor duplicated code
- Split monster methods
- Extract configuration
- Add unit tests
- Add security tests
- Improve error handling
- Standardize logging

---

## 🎯 RELEASE CRITERIA

### Minimum Viable Product (MVP)
- ✅ All CRITICAL issues fixed (Week 1-2)
- ✅ All HIGH priority UX issues fixed
- ✅ Basic test coverage for critical paths
- ✅ Security documentation for users

### Beta Release
- ✅ All MEDIUM priority issues fixed
- ✅ Comprehensive error handling
- ✅ User documentation complete
- ✅ Security audit passed

### Production Release
- ✅ Technical debt addressed
- ✅ Full test suite (unit + integration + security)
- ✅ Performance benchmarks
- ✅ Code review passed
- ✅ Beta testing completed

---

## 📝 NOTES

**Current Status:** Post code review - critical issues identified
**Commits Reviewed:** a34eac3 (Phase 1), 76c0dfc (Phase 2)
**Overall Assessment:** C+ (75/100) - Functional but has critical gaps

**DO NOT RELEASE** in current state - critical bugs cause:
- Corrupted audiobooks
- Data loss
- Security vulnerabilities
- Wasted user time

**Required for production:** Fix all CRITICAL and HIGH issues + comprehensive testing