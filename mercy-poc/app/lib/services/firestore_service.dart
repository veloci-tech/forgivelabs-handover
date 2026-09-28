import 'package:cloud_firestore/cloud_firestore.dart';
import '../config/app_config.dart';
import '../models/session.dart';
import '../models/metrics.dart';

class FirestoreService {
  final FirebaseFirestore _firestore;

  FirestoreService({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> get _sessionsRef =>
      _firestore.collection(AppConfig.sessionsCollection);

  // --- Sessions ---

  Future<Session> createSession(String userId) async {
    final docRef = await _sessionsRef.add({
      'userId': userId,
      'startTime': FieldValue.serverTimestamp(),
      'transcript': [],
      'safetyFlags': [],
      'status': SessionStatus.active.name,
    });
    final snapshot = await docRef.get();
    return Session.fromFirestore(snapshot);
  }

  Future<void> endSession(String sessionId) async {
    await _sessionsRef.doc(sessionId).update({
      'endTime': FieldValue.serverTimestamp(),
      'status': SessionStatus.completed.name,
    });
  }

  Future<void> markSessionError(String sessionId) async {
    await _sessionsRef.doc(sessionId).update({
      'endTime': FieldValue.serverTimestamp(),
      'status': SessionStatus.error.name,
    });
  }

  Future<void> appendTranscript(
    String sessionId,
    TranscriptEntry entry,
  ) async {
    await _sessionsRef.doc(sessionId).update({
      'transcript': FieldValue.arrayUnion([entry.toMap()]),
    });
  }

  Future<void> addSafetyFlag(String sessionId, String flag) async {
    await _sessionsRef.doc(sessionId).update({
      'safetyFlags': FieldValue.arrayUnion([flag]),
    });
  }

  Stream<Session> streamSession(String sessionId) {
    return _sessionsRef
        .doc(sessionId)
        .snapshots()
        .map((snap) => Session.fromFirestore(snap));
  }

  Stream<List<Session>> streamRecentSessions({int limit = 20}) {
    return _sessionsRef
        .orderBy('startTime', descending: true)
        .limit(limit)
        .snapshots()
        .map((snap) =>
            snap.docs.map((doc) => Session.fromFirestore(doc)).toList());
  }

  // --- Metrics ---

  Future<Metrics> fetchMetrics() async {
    final snapshot = await _sessionsRef.get();
    final sessions =
        snapshot.docs.map((doc) => Session.fromFirestore(doc)).toList();

    if (sessions.isEmpty) return Metrics.empty();

    final completed = sessions
        .where((s) => s.status == SessionStatus.completed)
        .toList();
    final errors =
        sessions.where((s) => s.status == SessionStatus.error).toList();
    final active =
        sessions.where((s) => s.status == SessionStatus.active).toList();

    final totalDurationSeconds = completed.fold<int>(0, (sum, s) {
      return sum + (s.duration?.inSeconds ?? 0);
    });

    final avgDuration = completed.isNotEmpty
        ? Duration(seconds: totalDurationSeconds ~/ completed.length)
        : Duration.zero;

    final errorRate =
        sessions.isNotEmpty ? errors.length / sessions.length : 0.0;

    final safetyFlagCount =
        sessions.fold<int>(0, (sum, s) => sum + s.safetyFlags.length);

    return Metrics(
      totalSessions: sessions.length,
      avgDuration: avgDuration,
      errorRate: errorRate,
      safetyFlagCount: safetyFlagCount,
      activeSessions: active.length,
    );
  }

  Future<List<Session>> fetchRecentSessions({int limit = 20}) async {
    final snapshot = await _sessionsRef
        .orderBy('startTime', descending: true)
        .limit(limit)
        .get();
    return snapshot.docs
        .map((doc) => Session.fromFirestore(doc))
        .toList();
  }
}
