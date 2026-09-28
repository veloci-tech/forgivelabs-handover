import 'package:cloud_firestore/cloud_firestore.dart';

enum SessionStatus { active, completed, error }

class TranscriptEntry {
  final String role;
  final String text;
  final DateTime timestamp;

  const TranscriptEntry({
    required this.role,
    required this.text,
    required this.timestamp,
  });

  factory TranscriptEntry.fromMap(Map<String, dynamic> map) {
    return TranscriptEntry(
      role: map['role'] as String? ?? 'unknown',
      text: map['text'] as String? ?? '',
      timestamp: (map['timestamp'] as Timestamp?)?.toDate() ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'role': role,
      'text': text,
      'timestamp': Timestamp.fromDate(timestamp),
    };
  }
}

class Session {
  final String id;
  final String userId;
  final DateTime startTime;
  final DateTime? endTime;
  final List<TranscriptEntry> transcript;
  final List<String> safetyFlags;
  final SessionStatus status;

  const Session({
    required this.id,
    required this.userId,
    required this.startTime,
    this.endTime,
    this.transcript = const [],
    this.safetyFlags = const [],
    this.status = SessionStatus.active,
  });

  Duration? get duration {
    if (endTime == null) return null;
    return endTime!.difference(startTime);
  }

  bool get hasSafetyFlags => safetyFlags.isNotEmpty;

  factory Session.fromFirestore(DocumentSnapshot doc) {
    final data = doc.data() as Map<String, dynamic>? ?? {};
    return Session(
      id: doc.id,
      userId: data['userId'] as String? ?? '',
      startTime:
          (data['startTime'] as Timestamp?)?.toDate() ?? DateTime.now(),
      endTime: (data['endTime'] as Timestamp?)?.toDate(),
      transcript: (data['transcript'] as List<dynamic>?)
              ?.map((e) =>
                  TranscriptEntry.fromMap(e as Map<String, dynamic>))
              .toList() ??
          [],
      safetyFlags: (data['safetyFlags'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      status: SessionStatus.values.firstWhere(
        (s) => s.name == (data['status'] as String? ?? 'active'),
        orElse: () => SessionStatus.active,
      ),
    );
  }

  Map<String, dynamic> toFirestore() {
    return {
      'userId': userId,
      'startTime': Timestamp.fromDate(startTime),
      if (endTime != null) 'endTime': Timestamp.fromDate(endTime!),
      'transcript': transcript.map((t) => t.toMap()).toList(),
      'safetyFlags': safetyFlags,
      'status': status.name,
    };
  }

  Session copyWith({
    String? id,
    String? userId,
    DateTime? startTime,
    DateTime? endTime,
    List<TranscriptEntry>? transcript,
    List<String>? safetyFlags,
    SessionStatus? status,
  }) {
    return Session(
      id: id ?? this.id,
      userId: userId ?? this.userId,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      transcript: transcript ?? this.transcript,
      safetyFlags: safetyFlags ?? this.safetyFlags,
      status: status ?? this.status,
    );
  }
}
