import { useCallback, useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { AgentConfigLeftPanel } from "@/components/admin/agent-config-left-panel";
import { PlaygroundPreviewPanel } from "@/components/admin/playground-preview-panel";
import { useVoiceLiveInstances } from "@/hooks/use-voice-live-instances";
import type { HcpFormValues } from "@/pages/admin/hcp-profile-editor";
import type { HcpProfile } from "@/types/hcp";

interface VoiceAvatarTabProps {
  form: UseFormReturn<HcpFormValues>;
  profile?: HcpProfile;
  isNew: boolean;
}

export function VoiceAvatarTab({ form, profile, isNew }: VoiceAvatarTabProps) {
  // Auto-generated instructions from InstructionsSection (used as fallback systemPrompt)
  const [autoInstructions, setAutoInstructions] = useState("");
  const handleAutoInstructionsChange = useCallback((instructions: string) => {
    setAutoInstructions(instructions);
  }, []);

  // Resolve selected VL Instance to pass its avatar data to Playground
  const { data } = useVoiceLiveInstances();
  const instances = data?.items ?? [];
  const vlInstanceId = form.watch("voice_live_instance_id");
  const selectedInstance = instances.find((i) => i.id === vlInstanceId);
  // Voice mode is implied solely by having an assigned VL Instance (D-11)
  const voiceModeEnabled = Boolean(vlInstanceId);

  // systemPrompt: use override if set, otherwise use auto-generated instructions
  const overridePrompt = form.watch("agent_instructions_override");
  const systemPrompt = (overridePrompt && overridePrompt.trim()) ? overridePrompt : autoInstructions;

  return (
    <div className="flex h-[calc(100vh-14rem)] min-h-[480px]">
      {/* Left Panel: Agent Configuration — fixed width, scrollable, matching VL editor */}
      <div className="w-[380px] min-w-[340px] border-r overflow-y-auto p-4 space-y-4">
        <AgentConfigLeftPanel
          form={form}
          profile={profile}
          isNew={isNew}
          onAutoInstructionsChange={handleAutoInstructionsChange}
        />
      </div>
      {/* Right Panel: Playground Preview — fills remaining space, matching VL editor */}
      <div className="flex-1 flex flex-col min-w-0">
        <PlaygroundPreviewPanel
          hcpProfileId={profile?.id}
          profileName={profile?.name}
          agentId={profile?.agent_id}
          vlInstanceId={vlInstanceId ?? undefined}
          systemPrompt={systemPrompt}
          avatarCharacter={selectedInstance?.avatar_character}
          avatarStyle={selectedInstance?.avatar_style}
          avatarEnabled={selectedInstance?.avatar_enabled ?? false}
          voiceModeEnabled={voiceModeEnabled}
          disabled={isNew}
        />
      </div>
    </div>
  );
}
