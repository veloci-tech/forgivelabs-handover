class Metrics {
  final int totalSessions;
  final Duration avgDuration;
  final double errorRate;
  final int safetyFlagCount;
  final int activeSessions;

  const Metrics({
    required this.totalSessions,
    required this.avgDuration,
    required this.errorRate,
    required this.safetyFlagCount,
    this.activeSessions = 0,
  });

  factory Metrics.empty() {
    return const Metrics(
      totalSessions: 0,
      avgDuration: Duration.zero,
      errorRate: 0.0,
      safetyFlagCount: 0,
      activeSessions: 0,
    );
  }

  factory Metrics.fromMap(Map<String, dynamic> map) {
    return Metrics(
      totalSessions: map['totalSessions'] as int? ?? 0,
      avgDuration:
          Duration(seconds: map['avgDurationSeconds'] as int? ?? 0),
      errorRate: (map['errorRate'] as num?)?.toDouble() ?? 0.0,
      safetyFlagCount: map['safetyFlagCount'] as int? ?? 0,
      activeSessions: map['activeSessions'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'totalSessions': totalSessions,
      'avgDurationSeconds': avgDuration.inSeconds,
      'errorRate': errorRate,
      'safetyFlagCount': safetyFlagCount,
      'activeSessions': activeSessions,
    };
  }

  String get formattedAvgDuration {
    final minutes = avgDuration.inMinutes;
    final seconds = avgDuration.inSeconds % 60;
    return '${minutes}m ${seconds}s';
  }

  String get formattedErrorRate {
    return '${(errorRate * 100).toStringAsFixed(1)}%';
  }
}
