import { useEffect, useRef, type Ref } from "react";
import {
  ScrollArea,
  Avatar,
  AvatarFallback,
  Button,
} from "@/components/ui";
import { ChatBubble, ChatInput } from "@/components/shared";
import { AvatarView } from "@/components/voice/avatar-view";
import type { AudienceHcp } from "@/types/conference";
import type { AudioState } from "@/types/voice-live";

interface ChatMessage {
  id: string;
  sender: "hcp" | "mr";
  text: string;
  timestamp: Date;
  speakerName?: string;
  speakerColor?: string;
}

interface ConferenceStageProps {
  sessionId: string;
  onSendMessage: (text: string) => void;
  isStreaming: boolean;
  streamedText: string;
  currentSpeaker: string;
  currentSpeakerId?: string;
  avatarEnabled: boolean;
  featureAvatarEnabled: boolean;
  digitalHumanEnabled?: boolean;
  audienceHcps?: AudienceHcp[];
  avatarVideoRef?: Ref<HTMLVideoElement>;
  isAvatarConnected?: boolean;
  isAvatarConnecting?: boolean;
  avatarAudioState?: AudioState;
  avatarCharacter?: string;
  avatarStyle?: string;
  avatarHcpName?: string;
  activeAvatarHcpId?: string;
  onAvatarConnectClick?: () => void;
  messages?: ChatMessage[];
  inputMode?: "text" | "audio";
  onInputModeChange?: (mode: "text" | "audio") => void;
  onMicClick?: () => void;
  recordingState?: "idle" | "recording" | "processing";
  disabled?: boolean;
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function firstNonBlank(...values: Array<string | undefined>): string | undefined {
  return values.find((value) => value && value.trim());
}

export function ConferenceStage({
  onSendMessage,
  isStreaming,
  streamedText,
  currentSpeaker,
  currentSpeakerId,
  avatarEnabled,
  featureAvatarEnabled,
  digitalHumanEnabled = false,
  audienceHcps = [],
  avatarVideoRef,
  isAvatarConnected = false,
  isAvatarConnecting = false,
  avatarAudioState = "idle",
  avatarCharacter,
  avatarStyle,
  avatarHcpName,
  activeAvatarHcpId,
  onAvatarConnectClick,
  messages = [],
  inputMode = "text",
  onInputModeChange,
  onMicClick,
  recordingState = "idle",
  disabled = false,
}: ConferenceStageProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamedText]);

  const speakerInitials = currentSpeaker ? getInitials(currentSpeaker) : "AI";
  const showDigitalHuman = avatarEnabled && featureAvatarEnabled && digitalHumanEnabled;
  const showAudienceGallery = showDigitalHuman && audienceHcps.length > 0;
  const audienceGridClass =
    audienceHcps.length === 1
      ? "grid-cols-1"
      : audienceHcps.length === 2
        ? "grid-cols-2"
        : audienceHcps.length === 3
          ? "grid-cols-3"
          : "grid-cols-2";

  const isCurrentHcp = (hcp: AudienceHcp): boolean =>
    hcp.hcpProfileId === currentSpeakerId ||
    hcp.id === currentSpeakerId ||
    hcp.hcpName === currentSpeaker ||
    hcp.status === "speaking" ||
    (!currentSpeakerId &&
      !currentSpeaker &&
      Boolean(activeAvatarHcpId) &&
      (hcp.hcpProfileId === activeAvatarHcpId || hcp.id === activeAvatarHcpId));

  return (
    <div className="flex min-w-[480px] flex-1 flex-col">
      {/* Avatar area */}
      <div className="relative flex h-[240px] flex-col items-center justify-center bg-slate-900">
        {showAudienceGallery && avatarVideoRef ? (
          <div className={`grid h-full w-full ${audienceGridClass} gap-2 p-2`}>
            {audienceHcps.map((hcp) => {
              const isActive = isCurrentHcp(hcp);
              const displayName = hcp.hcpName || hcp.hcpProfileId || hcp.id;
              const resolvedAvatarCharacter = firstNonBlank(
                hcp.avatarCharacter,
                avatarCharacter,
                "lori",
              );
              const resolvedAvatarStyle = firstNonBlank(
                hcp.avatarStyle,
                avatarStyle,
                "casual",
              );

              return (
                <div
                  key={hcp.hcpProfileId || hcp.id || displayName}
                  data-testid={`audience-stage-${hcp.hcpProfileId || hcp.id}`}
                  data-active={isActive ? "true" : "false"}
                  className={[
                    "relative min-h-0 overflow-hidden rounded-lg border bg-slate-900",
                    isActive ? "border-cyan-300/80" : "border-white/10",
                  ].join(" ")}
                >
                  {isActive ? (
                    <AvatarView
                      videoRef={avatarVideoRef}
                      isAvatarConnected={isAvatarConnected}
                      isSessionActive={isAvatarConnected || isAvatarConnecting}
                      audioState={avatarAudioState}
                      isConnecting={isAvatarConnecting}
                      isDigitalHumanMode={true}
                      hcpName={displayName}
                      isFullScreen={false}
                      avatarCharacter={resolvedAvatarCharacter}
                      avatarStyle={resolvedAvatarStyle}
                      videoFit="contain"
                      className="!min-h-0 h-full w-full bg-slate-900"
                    />
                  ) : (
                    <AvatarView
                      videoRef={{ current: null }}
                      isAvatarConnected={false}
                      isSessionActive={false}
                      audioState="idle"
                      isConnecting={false}
                      isDigitalHumanMode={true}
                      hcpName={displayName}
                      isFullScreen={false}
                      avatarCharacter={resolvedAvatarCharacter}
                      avatarStyle={resolvedAvatarStyle}
                      videoFit="contain"
                      className="!min-h-0 h-full w-full bg-slate-900"
                    />
                  )}
                </div>
              );
            })}
          </div>
        ) : showDigitalHuman && avatarVideoRef ? (
          <AvatarView
            videoRef={avatarVideoRef}
            isAvatarConnected={isAvatarConnected}
            isSessionActive={isAvatarConnected || isAvatarConnecting}
            audioState={avatarAudioState}
            isConnecting={isAvatarConnecting}
            isDigitalHumanMode={true}
            hcpName={currentSpeaker || avatarHcpName || ""}
            isFullScreen={false}
            avatarCharacter={avatarCharacter}
            avatarStyle={avatarStyle}
            videoFit="contain"
            className="!min-h-0 h-full w-full bg-slate-900"
          />
        ) : null}
        {showDigitalHuman && !isAvatarConnected && onAvatarConnectClick && (
          <div className="absolute inset-x-0 bottom-4 z-30 flex justify-center">
            <Button
              type="button"
              size="sm"
              onClick={onAvatarConnectClick}
              disabled={isAvatarConnecting || disabled}
              className="shadow-lg"
            >
              {isAvatarConnecting ? "数字人连接中" : "连接数字人"}
            </Button>
          </div>
        )}
        {avatarEnabled && !showDigitalHuman && (
          <>
            <Avatar className="size-20">
              <AvatarFallback className="bg-primary text-primary-foreground text-2xl">
                {speakerInitials}
              </AvatarFallback>
            </Avatar>
            {currentSpeaker && (
              <p className="mt-2 text-sm text-slate-300">{currentSpeaker}</p>
            )}
          </>
        )}
        {!avatarEnabled && (
          <p className="text-sm text-slate-400">
            {currentSpeaker || "Conference Stage"}
          </p>
        )}
      </div>

      {/* Chat / Response area */}
      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {messages.map((msg) => (
            <ChatBubble
              key={msg.id}
              sender={msg.sender}
              text={msg.text}
              timestamp={msg.timestamp}
              speakerName={msg.speakerName}
              speakerColor={msg.speakerColor}
            />
          ))}

          {/* Streaming text indicator */}
          {isStreaming && streamedText && (
            <div className="flex justify-start">
              <div className="max-w-[75%]">
                <div className="rounded-2xl rounded-tl-sm bg-primary px-4 py-2 text-primary-foreground">
                  <p className="whitespace-pre-wrap text-sm">{streamedText}</p>
                </div>
              </div>
            </div>
          )}

          {/* Typing indicator */}
          {isStreaming && !streamedText && (
            <div className="flex justify-start">
              <div className="max-w-[75%]">
                <div className="rounded-2xl rounded-tl-sm bg-primary px-4 py-3">
                  <div className="flex items-center gap-1">
                    <span
                      className="inline-block size-2 animate-bounce rounded-full bg-primary-foreground"
                      style={{ animationDelay: "0ms" }}
                    />
                    <span
                      className="inline-block size-2 animate-bounce rounded-full bg-primary-foreground"
                      style={{ animationDelay: "150ms" }}
                    />
                    <span
                      className="inline-block size-2 animate-bounce rounded-full bg-primary-foreground"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t p-4">
        <ChatInput
          onSend={onSendMessage}
          inputMode={inputMode}
          onInputModeChange={onInputModeChange}
          onMicClick={onMicClick ?? (() => {})}
          recordingState={recordingState}
          disabled={disabled}
        />
      </div>
    </div>
  );
}
