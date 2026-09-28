import 'dart:async';
import 'dart:typed_data';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

import '../config/app_config.dart';
import '../models/session.dart';
import '../services/firestore_service.dart';

enum VoiceAgentState { idle, listening, processing, speaking, error }

class VoiceService extends ChangeNotifier {
  final FirestoreService _firestoreService;
  final FirebaseFunctions _functions;
  final AudioRecorder _recorder;

  VoiceAgentState _state = VoiceAgentState.idle;
  Session? _currentSession;
  String _lastUserText = '';
  String _lastAgentText = '';
  String? _errorMessage;
  bool _safetyFlagged = false;
  StreamSubscription<Session>? _sessionSubscription;

  VoiceService({
    FirestoreService? firestoreService,
    FirebaseFunctions? functions,
    AudioRecorder? recorder,
  })  : _firestoreService = firestoreService ?? FirestoreService(),
        _functions = functions ??
            FirebaseFunctions.instanceFor(region: AppConfig.functionsRegion),
        _recorder = recorder ?? AudioRecorder();

  VoiceAgentState get state => _state;
  Session? get currentSession => _currentSession;
  String get lastUserText => _lastUserText;
  String get lastAgentText => _lastAgentText;
  String? get errorMessage => _errorMessage;
  bool get safetyFlagged => _safetyFlagged;
  bool get isRecording => _state == VoiceAgentState.listening;

  Future<void> startSession(String userId) async {
    try {
      _currentSession = await _firestoreService.createSession(userId);
      _listenToSession(_currentSession!.id);
      _setState(VoiceAgentState.idle);
    } catch (e) {
      _setError('Failed to start session: $e');
    }
  }

  void _listenToSession(String sessionId) {
    _sessionSubscription?.cancel();
    _sessionSubscription =
        _firestoreService.streamSession(sessionId).listen((session) {
      _currentSession = session;
      _safetyFlagged = session.hasSafetyFlags;
      notifyListeners();
    });
  }

  Future<void> startRecording() async {
    if (_currentSession == null) return;

    try {
      final hasPermission = await _recorder.hasPermission();
      if (!hasPermission) {
        _setError('Microphone permission denied');
        return;
      }

      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.wav),
        path: '',
      );
      _setState(VoiceAgentState.listening);
    } catch (e) {
      _setError('Failed to start recording: $e');
    }
  }

  Future<void> stopRecordingAndProcess() async {
    if (_state != VoiceAgentState.listening) return;

    try {
      final path = await _recorder.stop();
      if (path == null) {
        _setError('No audio recorded');
        return;
      }

      _setState(VoiceAgentState.processing);
      await _processVoicePipeline(path);
    } catch (e) {
      _setError('Failed to process recording: $e');
    }
  }

  Future<void> _processVoicePipeline(String audioPath) async {
    final sessionId = _currentSession!.id;

    try {
      // Step 1: Speech-to-Text
      final sttResult = await _callProcessVoice(audioPath);
      final userText = sttResult['text'] as String? ?? '';
      _lastUserText = userText;
      notifyListeners();

      await _firestoreService.appendTranscript(
        sessionId,
        TranscriptEntry(
          role: 'user',
          text: userText,
          timestamp: DateTime.now(),
        ),
      );

      // Step 2: LLM Response Generation
      final llmResult = await _callGenerateResponse(sessionId, userText);
      final agentText = llmResult['response'] as String? ?? '';
      final safetyFlag = llmResult['safetyFlag'] as String?;
      _lastAgentText = agentText;
      notifyListeners();

      if (safetyFlag != null && safetyFlag.isNotEmpty) {
        await _firestoreService.addSafetyFlag(sessionId, safetyFlag);
      }

      await _firestoreService.appendTranscript(
        sessionId,
        TranscriptEntry(
          role: 'agent',
          text: agentText,
          timestamp: DateTime.now(),
        ),
      );

      // Step 3: Text-to-Speech
      _setState(VoiceAgentState.speaking);
      await _callSynthesizeSpeech(agentText);

      _setState(VoiceAgentState.idle);
    } catch (e) {
      await _firestoreService.markSessionError(sessionId);
      _setError('Voice pipeline failed: $e');
    }
  }

  Future<Map<String, dynamic>> _callProcessVoice(String audioPath) async {
    final callable = _functions.httpsCallable('processVoice');
    final result = await callable.call<Map<String, dynamic>>({
      'sessionId': _currentSession!.id,
      'audioPath': audioPath,
    });
    return result.data;
  }

  Future<Map<String, dynamic>> _callGenerateResponse(
    String sessionId,
    String userText,
  ) async {
    final callable = _functions.httpsCallable('generateResponse');
    final result = await callable.call<Map<String, dynamic>>({
      'sessionId': sessionId,
      'text': userText,
    });
    return result.data;
  }

  Future<Uint8List?> _callSynthesizeSpeech(String text) async {
    final callable = _functions.httpsCallable('synthesizeSpeech');
    final result = await callable.call<Map<String, dynamic>>({
      'text': text,
    });
    final audioBase64 = result.data['audio'] as String?;
    if (audioBase64 == null) return null;
    // Audio playback would be handled by a platform-specific player
    return null;
  }

  Future<void> endSession() async {
    if (_currentSession == null) return;

    try {
      await _firestoreService.endSession(_currentSession!.id);
      _sessionSubscription?.cancel();
      _currentSession = null;
      _lastUserText = '';
      _lastAgentText = '';
      _safetyFlagged = false;
      _setState(VoiceAgentState.idle);
    } catch (e) {
      _setError('Failed to end session: $e');
    }
  }

  void _setState(VoiceAgentState newState) {
    _state = newState;
    _errorMessage = null;
    notifyListeners();
  }

  void _setError(String message) {
    _state = VoiceAgentState.error;
    _errorMessage = message;
    debugPrint('[VoiceService] Error: $message');
    notifyListeners();
  }

  void clearError() {
    if (_state == VoiceAgentState.error) {
      _setState(VoiceAgentState.idle);
    }
  }

  @override
  void dispose() {
    _sessionSubscription?.cancel();
    _recorder.dispose();
    super.dispose();
  }
}
