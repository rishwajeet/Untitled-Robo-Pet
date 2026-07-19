# OLED message UI

The message screen reserves its top 11 pixels for a pulsing chat icon, sender,
and optional page counter. The remaining area contains two 21-character,
word-wrapped lines. Long messages advance every 2.6 seconds and loop until the
downstream controller dismisses or replaces the notification.

Generate previews:

```bash
python3 assets/messages/generate_message_ui.py
```

Runtime rendering is implemented by
`firmware/uno_q_mcu/MessageDisplay.h`; no message-specific bitmaps are required.
