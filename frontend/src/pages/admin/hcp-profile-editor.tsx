import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { ArrowLeft, Save, MessageSquare, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PersonalitySliders } from "@/components/admin/personality-sliders";
import { ObjectionList } from "@/components/admin/objection-list";
import { TestChatDialog } from "@/components/admin/test-chat-dialog";
import { VoiceAvatarTab } from "@/components/admin/voice-avatar-tab";
import { AgentStatusSection } from "@/components/admin/agent-status-section";
import {
  useHcpProfile,
  useCreateHcpProfile,
  useUpdateHcpProfile,
  useRetrySyncHcpProfile,
} from "@/hooks/use-hcp-profiles";
import type { HcpProfileCreate, HcpProfileUpdate } from "@/types/hcp";

const SPECIALTIES = [
  "Oncology",
  "Hematology",
  "Immunology",
  "Neurology",
  "Cardiology",
  "Endocrinology",
  "Dermatology",
  "Gastroenterology",
  "General Practice",
];

const DIFFICULTIES = ["easy", "medium", "hard"] as const;

export const hcpSchema = z.object({
  name: z.string().min(1),
  specialty: z.string().min(1),
  hospital: z.string().default(""),
  title: z.string().default(""),
  personality_type: z.enum([
    "friendly",
    "skeptical",
    "busy",
    "analytical",
    "cautious",
  ]),
  emotional_state: z.number().min(0).max(100),
  communication_style: z.number().min(0).max(100),
  expertise_areas: z.array(z.string()),
  prescribing_habits: z.string().default(""),
  concerns: z.string().default(""),
  objections: z.array(z.string()),
  probe_topics: z.array(z.string()),
  difficulty: z.enum(["easy", "medium", "hard"]),
  // Voice Live Instance reference (D-10/D-13 -- required on save, both create and edit)
  voice_live_instance_id: z
    .string()
    .nullable()
    .refine((val) => Boolean(val && val.length > 0), {
      message: "hcp.vlInstanceValidationError",
    }),
  agent_instructions_override: z.string().default(""),
});

export type HcpFormValues = z.infer<typeof hcpSchema>;

export default function HcpProfileEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation(["admin", "common"]);
  const isNew = !id;

  const { data: profile, isLoading: profileLoading } = useHcpProfile(id);
  const createMutation = useCreateHcpProfile();
  const updateMutation = useUpdateHcpProfile();
  const retrySyncMutation = useRetrySyncHcpProfile();

  const [testChatOpen, setTestChatOpen] = useState(false);

  const VALID_TABS = new Set(["profile", "voice-avatar"]);
  const [activeTab, setActiveTab] = useState("profile");
  const handleTabChange = (value: string) => {
    setActiveTab(VALID_TABS.has(value) ? value : "profile");
  };

  const form = useForm<HcpFormValues>({
    resolver: zodResolver(hcpSchema) as Resolver<HcpFormValues>,
    defaultValues: {
      name: "",
      specialty: "",
      hospital: "",
      title: "",
      personality_type: "friendly",
      emotional_state: 30,
      communication_style: 50,
      expertise_areas: [],
      prescribing_habits: "",
      concerns: "",
      objections: [],
      probe_topics: [],
      difficulty: "medium",
      voice_live_instance_id: null,
      agent_instructions_override: "",
    },
  });

  useEffect(() => {
    if (profile) {
      form.reset({
        name: profile.name,
        specialty: profile.specialty,
        hospital: profile.hospital ?? "",
        title: profile.title ?? "",
        personality_type: profile.personality_type,
        emotional_state: profile.emotional_state,
        communication_style: profile.communication_style,
        expertise_areas: profile.expertise_areas,
        prescribing_habits: profile.prescribing_habits ?? "",
        concerns: profile.concerns ?? "",
        objections: profile.objections,
        probe_topics: profile.probe_topics,
        difficulty: profile.difficulty,
        voice_live_instance_id: profile.voice_live_instance_id ?? null,
        agent_instructions_override:
          profile.agent_instructions_override ?? "",
      });
    }
  }, [profile, form]);

  const handleSubmit = (values: HcpFormValues) => {
    const data = {
      ...values,
      expertise_areas: values.expertise_areas.filter(Boolean),
      objections: values.objections.filter(Boolean),
      probe_topics: values.probe_topics.filter(Boolean),
    };

    if (isNew) {
      createMutation.mutate(data as HcpProfileCreate, {
        onSuccess: () => {
          toast.success(t("admin:hcp.save"));
          navigate("/admin/hcp-profiles");
        },
        onError: () => toast.error(t("admin:errors.hcpSaveFailed")),
      });
    } else if (id) {
      updateMutation.mutate(
        { id, data: data as HcpProfileUpdate },
        {
          onSuccess: () => {
            toast.success(t("admin:hcp.save"));
            navigate("/admin/hcp-profiles");
          },
          onError: () => toast.error(t("admin:errors.hcpSaveFailed")),
        },
      );
    }
  };

  const handleInvalidSubmit = (errors: typeof form.formState.errors) => {
    if (errors.voice_live_instance_id) {
      toast.error(t("admin:hcp.vlInstanceSaveBlockedToast"));
    }
  };

  const handleRetrySync = () => {
    if (!id) return;
    retrySyncMutation.mutate(id, {
      onSuccess: () => toast.success(t("admin:hcp.syncSuccess")),
      onError: (err) =>
        toast.error(
          t("admin:hcp.syncFailed", { error: (err as Error).message }),
        ),
    });
  };

  const watchName = form.watch("name") ?? "";
  const getInitials = (name: string) =>
    name
      ? name
          .split(" ")
          .map((n) => n[0])
          .join("")
          .toUpperCase()
          .slice(0, 2) || "?"
      : "?";

  if (!isNew && profileLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/admin/hcp-profiles")}
        >
          <ArrowLeft className="size-5" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">
            {isNew
              ? t("admin:hcp.createButton")
              : `${t("admin:hcp.save")} - ${profile?.name ?? ""}`}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={form.handleSubmit(handleSubmit, handleInvalidSubmit)}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            <Save className="size-4 mr-2" />
            {createMutation.isPending || updateMutation.isPending
              ? t("common:saving")
              : t("admin:hcp.save")}
          </Button>
        </div>
      </div>

      {/* Form wraps entire Tabs so state persists across tab switches */}
      <Form {...form}>
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList className="w-full bg-muted/60 border">
            <TabsTrigger
              value="profile"
              className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
            >
              {t("admin:hcp.tabProfile")}
            </TabsTrigger>
            <TabsTrigger
              value="voice-avatar"
              className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
            >
              {t("admin:hcp.tabVoiceAvatar")}
            </TabsTrigger>
          </TabsList>

          {/* Profile Tab */}
          <TabsContent value="profile" className="mt-4">
            <div className="space-y-6">
              {/* Top row: Identity + Agent Status side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Identity Card — spans 2 columns */}
                <Card className="lg:col-span-2">
                  <CardHeader>
                    <CardTitle className="text-base font-semibold">
                      {t("admin:hcp.identity")}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-start gap-6">
                      <Avatar className="size-20 shrink-0">
                        <AvatarFallback className="bg-blue-600 text-white text-2xl font-semibold">
                          {getInitials(watchName)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="grid grid-cols-2 gap-4 flex-1">
                        <FormField
                          control={form.control}
                          name="name"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t("admin:hcp.name")} *</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="specialty"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t("admin:hcp.specialty")} *</FormLabel>
                              <Select
                                value={field.value}
                                onValueChange={field.onChange}
                              >
                                <FormControl>
                                  <SelectTrigger>
                                    <SelectValue placeholder={t("admin:hcp.selectSpecialty")} />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  {SPECIALTIES.map((s) => (
                                    <SelectItem key={s} value={s}>
                                      {s}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="hospital"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t("admin:hcp.hospital")}</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="title"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t("admin:hcp.titleField")}</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                            </FormItem>
                          )}
                        />
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Agent Status + Test Chat — right column */}
                <div className="space-y-4">
                  <AgentStatusSection
                    profile={profile}
                    isNew={isNew}
                    onRetrySync={handleRetrySync}
                    retrySyncPending={retrySyncMutation.isPending}
                  />
                  {!isNew && profile && (
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => setTestChatOpen(true)}
                    >
                      <MessageSquare className="size-4 mr-2" />
                      {t("admin:hcp.testChat")}
                    </Button>
                  )}
                </div>
              </div>

              {/* Personality Card */}
              <PersonalitySliders
                personalityType={form.watch("personality_type")}
                emotionalState={form.watch("emotional_state")}
                communicationStyle={form.watch("communication_style")}
                onPersonalityTypeChange={(v) =>
                  form.setValue(
                    "personality_type",
                    v as HcpFormValues["personality_type"],
                  )
                }
                onEmotionalStateChange={(v) =>
                  form.setValue("emotional_state", v)
                }
                onCommunicationStyleChange={(v) =>
                  form.setValue("communication_style", v)
                }
              />

              {/* Knowledge Card */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-semibold">
                    {t("admin:hcp.knowledge")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-2">
                    <Label>{t("admin:hcp.expertiseAreas")}</Label>
                    <Input
                      value={(form.watch("expertise_areas") ?? []).join(", ")}
                      onChange={(e) =>
                        form.setValue(
                          "expertise_areas",
                          e.target.value.split(",").map((s) => s.trim()),
                        )
                      }
                      placeholder={t("admin:hcp.expertiseAreasPlaceholder")}
                    />
                  </div>
                  <FormField
                    control={form.control}
                    name="prescribing_habits"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {t("admin:hcp.prescribingHabits")}
                        </FormLabel>
                        <FormControl>
                          <Textarea rows={3} {...field} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="concerns"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t("admin:hcp.concerns")}</FormLabel>
                        <FormControl>
                          <Textarea rows={3} {...field} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              {/* Interaction Rules Card */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-semibold">
                    {t("admin:hcp.interactionRules")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ObjectionList
                    items={form.watch("objections") ?? []}
                    onChange={(items) => form.setValue("objections", items)}
                    label={t("admin:hcp.objections")}
                    addLabel={t("admin:hcp.addObjection")}
                  />
                  <ObjectionList
                    items={form.watch("probe_topics") ?? []}
                    onChange={(items) =>
                      form.setValue("probe_topics", items)
                    }
                    label={t("admin:hcp.probeTopics")}
                    addLabel={t("admin:hcp.addTopic")}
                  />
                  <div className="grid gap-2">
                    <Label>{t("admin:hcp.difficulty")}</Label>
                    <div className="flex items-center gap-4">
                      {DIFFICULTIES.map((d) => (
                        <label
                          key={d}
                          className="flex items-center gap-2 cursor-pointer"
                        >
                          <input
                            type="radio"
                            name="difficulty"
                            value={d}
                            checked={form.watch("difficulty") === d}
                            onChange={() => form.setValue("difficulty", d)}
                            className="accent-primary"
                          />
                          <span className="text-sm capitalize">{t(`common:difficulty${d.charAt(0).toUpperCase() + d.slice(1)}`)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>

            </div>
          </TabsContent>

          {/* Voice & Avatar Tab */}
          <TabsContent value="voice-avatar" className="mt-4">
            <VoiceAvatarTab form={form} profile={profile} isNew={isNew} />
          </TabsContent>

        </Tabs>
      </Form>

      {/* Test Chat Dialog */}
      {!isNew && profile && (
        <TestChatDialog
          profileId={profile.id}
          profileName={profile.name}
          personalityType={profile.personality_type}
          agentId={profile.agent_id}
          agentVersion={profile.agent_version}
          open={testChatOpen}
          onOpenChange={setTestChatOpen}
        />
      )}
    </div>
  );
}
