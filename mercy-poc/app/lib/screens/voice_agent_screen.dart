import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/session.dart';
import '../services/voice_service.dart';

class VoiceAgentScreen extends StatefulWidget {
  const VoiceAgentScreen({super.key});

  @override
  State<VoiceAgentScreen> createState() => _VoiceAgentScreenState();
}

class _VoiceAgentScreenState extends State<VoiceAgentScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.2).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final voice = context.read<VoiceService>();
      voice.startSession('anonymous');
    });
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Consumer<VoiceService>(
      builder: (context, voice, _) {
        _syncPulseAnimation(voice.state);

        return Scaffold(
          appBar: AppBar(
            title: const Text('Voice Agent'),
            centerTitle: true,
            actions: [
              if (voice.safetyFlagged) _SafetyBadge(),
              if (voice.currentSession != null)
                IconButton(
                  icon: const Icon(Icons.stop_circle_outlined),
                  tooltip: 'End Session',
                  onPressed: voice.endSession,
                ),
            ],
          ),
          body: SafeArea(
            child: Column(
              children: [
                _StatusBar(state: voice.state),
                Expanded(
                  child: _TranscriptView(
                    session: voice.currentSession,
                    lastUserText: voice.lastUserText,
                    lastAgentText: voice.lastAgentText,
                  ),
                ),
                if (voice.errorMessage != null)
                  _ErrorBanner(
                    message: voice.errorMessage!,
                    onDismiss: voice.clearError,
                  ),
                _MicControls(
                  state: voice.state,
                  pulseAnimation: _pulseAnimation,
                  onPressStart: voice.startRecording,
                  onPressEnd: voice.stopRecordingAndProcess,
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        );
      },
    );
  }

  void _syncPulseAnimation(VoiceAgentState state) {
    if (state == VoiceAgentState.listening) {
      if (!_pulseController.isAnimating) _pulseController.repeat(reverse: true);
    } else {
      if (_pulseController.isAnimating) _pulseController.stop();
    }
  }
}

class _StatusBar extends StatelessWidget {
  final VoiceAgentState state;

  const _StatusBar({required this.state});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final (label, color, icon) = switch (state) {
      VoiceAgentState.idle => ('Ready', theme.colorScheme.outline, Icons.circle_outlined),
      VoiceAgentState.listening => ('Listening...', theme.colorScheme.error, Icons.hearing_rounded),
      VoiceAgentState.processing => ('Processing...', theme.colorScheme.tertiary, Icons.psychology_rounded),
      VoiceAgentState.speaking => ('Speaking...', theme.colorScheme.primary, Icons.volume_up_rounded),
      VoiceAgentState.error => ('Error', theme.colorScheme.error, Icons.error_outline_rounded),
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        border: Border(bottom: BorderSide(color: color.withOpacity(0.2))),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Text(
            label,
            style: theme.textTheme.labelLarge?.copyWith(
              color: color,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (state == VoiceAgentState.processing ||
              state == VoiceAgentState.speaking) ...[
            const SizedBox(width: 8),
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: color,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TranscriptView extends StatelessWidget {
  final Session? session;
  final String lastUserText;
  final String lastAgentText;

  const _TranscriptView({
    required this.session,
    required this.lastUserText,
    required this.lastAgentText,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final transcript = session?.transcript ?? [];

    if (transcript.isEmpty && lastUserText.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.mic_none_rounded,
              size: 64,
              color: theme.colorScheme.outlineVariant,
            ),
            const SizedBox(height: 16),
            Text(
              'Hold the mic button to speak',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      reverse: true,
      itemCount: transcript.length,
      itemBuilder: (context, index) {
        final entry = transcript[transcript.length - 1 - index];
        final isUser = entry.role == 'user';

        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.75,
            ),
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: isUser
                  ? theme.colorScheme.primaryContainer
                  : theme.colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(16),
                topRight: const Radius.circular(16),
                bottomLeft: Radius.circular(isUser ? 16 : 4),
                bottomRight: Radius.circular(isUser ? 4 : 16),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isUser ? 'You' : 'Mercy',
                  style: theme.textTheme.labelSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: isUser
                        ? theme.colorScheme.onPrimaryContainer
                        : theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  entry.text,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: isUser
                        ? theme.colorScheme.onPrimaryContainer
                        : theme.colorScheme.onSurface,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  final VoidCallback onDismiss;

  const _ErrorBanner({required this.message, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded,
              size: 20, color: theme.colorScheme.onErrorContainer),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onErrorContainer,
              ),
            ),
          ),
          IconButton(
            icon: Icon(Icons.close,
                size: 18, color: theme.colorScheme.onErrorContainer),
            onPressed: onDismiss,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
          ),
        ],
      ),
    );
  }
}

class _MicControls extends StatelessWidget {
  final VoiceAgentState state;
  final Animation<double> pulseAnimation;
  final VoidCallback onPressStart;
  final VoidCallback onPressEnd;

  const _MicControls({
    required this.state,
    required this.pulseAnimation,
    required this.onPressStart,
    required this.onPressEnd,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isListening = state == VoiceAgentState.listening;
    final isDisabled =
        state == VoiceAgentState.processing || state == VoiceAgentState.speaking;

    return Column(
      children: [
        const SizedBox(height: 16),
        GestureDetector(
          onLongPressStart: isDisabled ? null : (_) => onPressStart(),
          onLongPressEnd: isDisabled ? null : (_) => onPressEnd(),
          child: AnimatedBuilder(
            animation: pulseAnimation,
            builder: (context, child) => Transform.scale(
              scale: isListening ? pulseAnimation.value : 1.0,
              child: child,
            ),
            child: Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isListening
                    ? theme.colorScheme.error
                    : isDisabled
                        ? theme.colorScheme.surfaceContainerHighest
                        : theme.colorScheme.primary,
                boxShadow: isListening
                    ? [
                        BoxShadow(
                          color: theme.colorScheme.error.withOpacity(0.3),
                          blurRadius: 24,
                          spreadRadius: 4,
                        ),
                      ]
                    : [
                        BoxShadow(
                          color: theme.colorScheme.primary.withOpacity(0.2),
                          blurRadius: 12,
                          spreadRadius: 2,
                        ),
                      ],
              ),
              child: Icon(
                isListening ? Icons.mic : Icons.mic_none_rounded,
                size: 36,
                color: isDisabled
                    ? theme.colorScheme.onSurfaceVariant
                    : Colors.white,
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          isListening
              ? 'Release to send'
              : isDisabled
                  ? 'Please wait...'
                  : 'Hold to speak',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

class _SafetyBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Tooltip(
        message: 'Safety flags detected in this session',
        child: Chip(
          avatar: Icon(
            Icons.shield_rounded,
            size: 16,
            color: theme.colorScheme.onTertiaryContainer,
          ),
          label: Text(
            'Safety',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onTertiaryContainer,
            ),
          ),
          backgroundColor: theme.colorScheme.tertiaryContainer,
          side: BorderSide.none,
          padding: const EdgeInsets.symmetric(horizontal: 4),
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      ),
    );
  }
}

