class AppConfig {
  static const String appName = 'Mercy Voice AI';

  static const String functionsRegion = String.fromEnvironment(
    'FUNCTIONS_REGION',
    defaultValue: 'us-central1',
  );

  static const String firebaseProjectId = String.fromEnvironment(
    'FIREBASE_PROJECT_ID',
    defaultValue: 'mercy-poc',
  );

  static const bool useEmulators = bool.fromEnvironment(
    'USE_EMULATORS',
    defaultValue: false,
  );

  static const String emulatorHost = String.fromEnvironment(
    'EMULATOR_HOST',
    defaultValue: 'localhost',
  );

  static const int firestoreEmulatorPort = int.fromEnvironment(
    'FIRESTORE_EMULATOR_PORT',
    defaultValue: 8080,
  );

  static const int functionsEmulatorPort = int.fromEnvironment(
    'FUNCTIONS_EMULATOR_PORT',
    defaultValue: 5001,
  );

  static const int authEmulatorPort = int.fromEnvironment(
    'AUTH_EMULATOR_PORT',
    defaultValue: 9099,
  );

  static const int maxRecordingDurationSeconds = 60;
  static const int sessionTimeoutMinutes = 30;

  static const String collectionsPrefix = String.fromEnvironment(
    'COLLECTIONS_PREFIX',
    defaultValue: '',
  );

  static String get sessionsCollection => '${collectionsPrefix}sessions';
  static String get metricsCollection => '${collectionsPrefix}metrics';
  static String get usersCollection => '${collectionsPrefix}users';
}
