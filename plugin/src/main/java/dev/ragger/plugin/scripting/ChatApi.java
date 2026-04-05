package dev.ragger.plugin.scripting;

import net.runelite.api.ChatMessageType;
import net.runelite.client.chat.ChatMessageManager;
import net.runelite.client.chat.QueuedMessage;

/**
 * Lua binding for sending messages to the RuneLite chat box.
 * Exposed as the global "chat" table in Lua scripts.
 *
 * Usage in Lua:
 *   chat:game("message")
 *   chat:console("message")
 *   chat:send(chat.BROADCAST, "message")
 */
public class ChatApi {

    // Message type constants
    public final ChatMessageType GAMEMESSAGE = ChatMessageType.GAMEMESSAGE;
    public final ChatMessageType CONSOLE = ChatMessageType.CONSOLE;
    public final ChatMessageType BROADCAST = ChatMessageType.BROADCAST;
    public final ChatMessageType PUBLICCHAT = ChatMessageType.PUBLICCHAT;
    public final ChatMessageType PRIVATECHAT = ChatMessageType.PRIVATECHAT;
    public final ChatMessageType PRIVATECHATOUT = ChatMessageType.PRIVATECHATOUT;
    public final ChatMessageType FRIENDSCHAT = ChatMessageType.FRIENDSCHAT;
    public final ChatMessageType FRIENDSCHATNOTIFICATION = ChatMessageType.FRIENDSCHATNOTIFICATION;
    public final ChatMessageType CLAN_CHAT = ChatMessageType.CLAN_CHAT;
    public final ChatMessageType CLAN_MESSAGE = ChatMessageType.CLAN_MESSAGE;
    public final ChatMessageType CLAN_GUEST_CHAT = ChatMessageType.CLAN_GUEST_CHAT;
    public final ChatMessageType CLAN_GUEST_MESSAGE = ChatMessageType.CLAN_GUEST_MESSAGE;
    public final ChatMessageType TRADE = ChatMessageType.TRADE;
    public final ChatMessageType TRADE_SENT = ChatMessageType.TRADE_SENT;
    public final ChatMessageType DIALOG = ChatMessageType.DIALOG;
    public final ChatMessageType MESBOX = ChatMessageType.MESBOX;
    public final ChatMessageType NPC_SAY = ChatMessageType.NPC_SAY;
    public final ChatMessageType ITEM_EXAMINE = ChatMessageType.ITEM_EXAMINE;
    public final ChatMessageType NPC_EXAMINE = ChatMessageType.NPC_EXAMINE;
    public final ChatMessageType OBJECT_EXAMINE = ChatMessageType.OBJECT_EXAMINE;
    public final ChatMessageType WELCOME = ChatMessageType.WELCOME;
    public final ChatMessageType LEVELUPMESSAGE = ChatMessageType.LEVELUPMESSAGE;
    public final ChatMessageType SPAM = ChatMessageType.SPAM;
    public final ChatMessageType AUTOTYPER = ChatMessageType.AUTOTYPER;

    private final ChatMessageManager chatMessageManager;

    public ChatApi(final ChatMessageManager chatMessageManager) {
        this.chatMessageManager = chatMessageManager;
    }

    public void game(final String message) {
        send(GAMEMESSAGE, message);
    }

    public void console(final String message) {
        send(CONSOLE, message);
    }

    public void send(final ChatMessageType type, final String message) {
        chatMessageManager.queue(QueuedMessage.builder()
            .type(type)
            .value(message)
            .build());
    }
}
