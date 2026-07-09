import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm, Controller, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { ArrowLeft, Save, RefreshCw, AlertTriangle, X, Plus, Info, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ObjectionList } from "@/components/admin/objection-list";
import {
  ConferenceAudienceConfig,
  MIN_AUDIENCE,
  MAX_AUDIENCE,
} from "@/components/admin/conference-audience-config";
import {
  useScenario,
  useCreateScenario,
  useUpdateScenario,
} from "@/hooks/use-scenarios";
import {
  useAudienceHcps,
  useSetAudienceHcps,
} from "@/hooks/use-conference-audience";
import { useHcpProfiles } from "@/hooks/use-hcp-profiles";
import { usePublishedSkills } from "@/hooks/use-skills";
import { useRubrics } from "@/hooks/use-rubrics";
import type { ConferencePromptConfig, ScenarioCreate, ScenarioUpdate } from "@/types/scenario";
import type { AudienceHcpCreate } from "@/types/conference";
import type { HcpProfile } from "@/types/hcp";
import type { Rubric } from "@/types/rubric";
import type { PromptOptimizerLocationState } from "./prompt-optimizer";

const AUDIENCE_PROMPT_OPTIMIZER_RESULT_KEY = "promptOptimizer:scenario:audiencePrompt";

/** Predefined tag categories with values. Will migrate to system_enums API in future. */
const PREDEFINED_TAGS: Record<string, string[]> = {
  product: ["Tislelizumab", "Zanubrutinib", "Pamiparib", "Lifirafenib", "Ociperlimab"],
  therapeutic_area: ["Oncology", "Hematology", "Immunology", "Solid Tumors"],
};

const DEFAULT_CONFERENCE_PROMPT_CONFIG: ConferencePromptConfig = {
  speaker_order_policy:
    "Use the configured audience order as the speaking order. The first non-moderator HCP is the primary questioner and should ask the most strategically important question. Later HCPs are secondary questioners and should cover different angles.",
  moderator_remarks: {
    invite: {
      zh: "欢迎参加本次会议。请先进行你的主题演讲，演讲结束后我会组织各位专家依次提问。",
      en: "Welcome to the meeting. Please begin your presentation first; afterward, I will invite each expert to ask questions in turn.",
    },
    opening: {
      zh: "感谢刚才的精彩演讲。下面进入问答环节，有请在座的各位专家依次提问。",
      en: "Thank you for the presentation. Let us now open the floor for questions from our panel.",
    },
    handoff: {
      zh: "感谢刚才的交流。下面有请下一位专家继续提问。",
      en: "Thank you for that exchange. I will now invite the next expert to ask a question.",
    },
    closing: {
      zh: "感谢各位专家的提问与精彩讨论，本次问答环节到此结束，谢谢大家。",
      en: "Thank you all for your questions and the insightful discussion. This concludes our Q&A session.",
    },
  },
  audience_prompt_template: `# Conference Audience Role
You are Dr. {hcp_name}, a {specialty} specialist attending a medical conference.
You are a {role} member in the audience.
Audience order: {speaker_order}. Speaker priority: {speaker_priority}.

# Speaking Policy
{speaker_order_policy}

# Personality
{personality_instruction}

# Presentation Context
The Medical Representative is presenting about: {product}
Therapeutic area: {therapeutic_area}
Presentation topic: {presentation_topic}

# Conversation So Far
{conversation_history}

# Questions Already Asked by Other Audience Members
{other_hcp_questions}

# Instructions
Respond as this HCP in a natural conference conversation with the MR.
- If you are taking the floor for the first time, ask one relevant question.
- If the MR has just answered you, acknowledge the answer and ask at most one contextual follow-up if needed.
- Do not repeat questions already asked by other HCPs.
- Respond in the same language the MR uses.
- Keep your response concise.
- Do NOT provide coaching feedback.`,
};

const moderatorRemarkSchema = z.object({ zh: z.string(), en: z.string() });
const conferencePromptConfigSchema = z.object({
  speaker_order_policy: z.string(),
  audience_prompt_template: z.string(),
  moderator_remarks: z.object({
    invite: moderatorRemarkSchema,
    opening: moderatorRemarkSchema,
    handoff: moderatorRemarkSchema,
    closing: moderatorRemarkSchema,
  }),
});

const scenarioSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().default(""),
  tags: z.array(z.string()),
  mode: z.enum(["f2f", "conference"]),
  difficulty: z.enum(["easy", "medium", "hard"]),
  hcp_profile_id: z.string().default(""),
  skill_id: z.string().min(1, "Skill is required"),
  key_messages: z.array(z.string()),
  conference_prompt_config: conferencePromptConfigSchema,
  rubric_id: z.string().min(1, "Scoring rubric is required"),
  pass_threshold: z.number().min(0).max(100),
}).superRefine((values, ctx) => {
  if (values.mode === "f2f" && !values.hcp_profile_id) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "HCP profile is required",
      path: ["hcp_profile_id"],
    });
  }
});

type ScenarioFormValues = z.infer<typeof scenarioSchema>;

const VALID_TABS = new Set(["basic", "linked", "scoring"]);

function isSameStringArray(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((value, index) => value === b[index]);
}

export default function ScenarioEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation(["admin", "common"]);
  const isNew = !id;

  const { data: scenario, isLoading: scenarioLoading } = useScenario(id);
  const createMutation = useCreateScenario();
  const updateMutation = useUpdateScenario();
  const { data: audienceData } = useAudienceHcps(id);
  const setAudienceMutation = useSetAudienceHcps();

  const { data: profilesData } = useHcpProfiles();
  const { data: publishedSkillsData } = usePublishedSkills();
  const { data: rubricsData } = useRubrics();

  const profiles: HcpProfile[] = useMemo(
    () => profilesData?.items ?? [],
    [profilesData],
  );
  const publishedSkills = useMemo(
    () => publishedSkillsData?.items ?? [],
    [publishedSkillsData],
  );
  const rubrics: Rubric[] = useMemo(() => rubricsData ?? [], [rubricsData]);

  const [activeTab, setActiveTab] = useState("basic");
  const handleTabChange = (value: string) => {
    setActiveTab(VALID_TABS.has(value) ? value : "basic");
  };

  const [customTagInput, setCustomTagInput] = useState("");

  const [audience, setAudience] = useState<AudienceHcpCreate[]>([]);

  const isArchived = scenario?.status === "archived";

  const form = useForm<ScenarioFormValues>({
    resolver: zodResolver(scenarioSchema) as Resolver<ScenarioFormValues>,
    defaultValues: {
      name: "",
      description: "",
      tags: [],
      mode: "f2f",
      difficulty: "medium",
      hcp_profile_id: "",
      skill_id: "",
      key_messages: [],
      conference_prompt_config: DEFAULT_CONFERENCE_PROMPT_CONFIG,
      rubric_id: "",
      pass_threshold: 70,
    },
  });

  useEffect(() => {
    if (scenario) {
      form.reset({
        name: scenario.name,
        description: scenario.description ?? "",
        tags: scenario.tags ?? [],
        mode: scenario.mode,
        difficulty: scenario.difficulty,
        hcp_profile_id: scenario.hcp_profile_id,
        skill_id: scenario.skill_id ?? "",
        key_messages: scenario.key_messages,
        conference_prompt_config:
          scenario.conference_prompt_config ?? DEFAULT_CONFERENCE_PROMPT_CONFIG,
        rubric_id: scenario.rubric_id,
        pass_threshold: scenario.pass_threshold,
      });
    }
  }, [scenario, form]);

  useEffect(() => {
    if (!isNew && !scenario) return;
    const optimizedText = sessionStorage.getItem(AUDIENCE_PROMPT_OPTIMIZER_RESULT_KEY);
    if (!optimizedText) return;
    sessionStorage.removeItem(AUDIENCE_PROMPT_OPTIMIZER_RESULT_KEY);
    form.setValue("conference_prompt_config.audience_prompt_template", optimizedText, {
      shouldDirty: true,
    });
  }, [form, isNew, scenario]);

  useEffect(() => {
    if (audienceData) {
      setAudience(
        audienceData.map((a) => ({
          hcpProfileId: a.hcpProfileId,
          roleInConference: a.roleInConference,
          voiceId: a.voiceId,
          sortOrder: a.sortOrder,
        })),
      );
    }
  }, [audienceData]);

  const validateAudience = (): boolean => {
    if (audience.length < MIN_AUDIENCE || audience.length > MAX_AUDIENCE) {
      toast.error(
        t("admin:scenarios.editor.audience.invalidCount", {
          min: MIN_AUDIENCE,
          max: MAX_AUDIENCE,
        }),
      );
      return false;
    }
    const ids = audience.map((a) => a.hcpProfileId);
    if (ids.some((x) => !x)) {
      toast.error(t("admin:scenarios.editor.audience.emptyHcp"));
      return false;
    }
    if (new Set(ids).size !== ids.length) {
      toast.error(t("admin:scenarios.editor.audience.duplicate"));
      return false;
    }
    if (!audience.some((member) => member.roleInConference === "moderator")) {
      toast.error(t("admin:scenarios.editor.audience.moderatorRequired"));
      return false;
    }
    return true;
  };

  const openAudiencePromptOptimizer = () => {
    const state: PromptOptimizerLocationState = {
      source: "text",
      returnTo: `${location.pathname}${location.search}`,
      resultStorageKey: AUDIENCE_PROMPT_OPTIMIZER_RESULT_KEY,
      content: form.getValues("conference_prompt_config.audience_prompt_template") ?? "",
      title: t("admin:scenarios.editor.conferencePrompt.hcpTemplateSection"),
    };
    navigate("/admin/prompt-optimizer", { state });
  };

  const saveAudienceThenFinish = (scenarioId: string, isConference: boolean) => {
    const finish = () => {
      toast.success(t("admin:scenarios.saved"));
      navigate("/admin/scenarios");
    };
    if (!isConference) {
      finish();
      return;
    }
    setAudienceMutation.mutate(
      { scenarioId, hcps: audience },
      {
        onSuccess: finish,
        onError: () =>
          toast.error(t("admin:scenarios.editor.audience.saveFailed")),
      },
    );
  };

  const handleSubmit = (values: ScenarioFormValues) => {
    const isConference = values.mode === "conference";

    if (isConference && !validateAudience()) return;

    const primaryConferenceHcp = isConference ? audience[0]?.hcpProfileId ?? "" : "";
    const hcpProfileId = isConference
      ? primaryConferenceHcp
      : values.hcp_profile_id;
    const normalizedKeyMessages = values.key_messages.filter(Boolean);

    const data: ScenarioCreate = {
      ...values,
      hcp_profile_id: hcpProfileId,
      key_messages: normalizedKeyMessages,
    };
    if (!isConference) {
      delete data.conference_prompt_config;
    }

    if (isNew) {
      createMutation.mutate(data, {
        onSuccess: (created) => saveAudienceThenFinish(created.id, isConference),
        onError: () => toast.error(t("scenarios.saveFailed")),
      });
    } else if (id) {
      const updateData: ScenarioUpdate = {};

      if (scenario) {
        const prevTags = scenario.tags ?? [];
        const nextTags = values.tags ?? [];
        const prevKeyMessages = scenario.key_messages ?? [];

        if (values.name !== scenario.name) updateData.name = values.name;
        if ((values.description ?? "") !== (scenario.description ?? "")) {
          updateData.description = values.description;
        }
        if (!isSameStringArray(nextTags, prevTags)) updateData.tags = nextTags;
        if (values.mode !== scenario.mode) updateData.mode = values.mode;
        if (values.difficulty !== scenario.difficulty) {
          updateData.difficulty = values.difficulty;
        }
        if (values.pass_threshold !== scenario.pass_threshold) {
          updateData.pass_threshold = values.pass_threshold;
        }

        const prevSkillId = scenario.skill_id ?? "";
        if ((values.skill_id ?? "") !== prevSkillId) {
          updateData.skill_id = values.skill_id;
        }
        if (values.rubric_id !== scenario.rubric_id) {
          updateData.rubric_id = values.rubric_id;
        }
        if (!isSameStringArray(normalizedKeyMessages, prevKeyMessages)) {
          updateData.key_messages = normalizedKeyMessages;
        }
        if (
          isConference &&
          JSON.stringify(values.conference_prompt_config) !==
            JSON.stringify(scenario.conference_prompt_config)
        ) {
          updateData.conference_prompt_config = values.conference_prompt_config;
        }

        // Conference mode uses audience bindings as source of truth; keep legacy
        // scenario.hcp_profile_id unchanged on update to avoid active-field conflicts.
        if (!isConference && hcpProfileId !== scenario.hcp_profile_id) {
          updateData.hcp_profile_id = hcpProfileId;
        }
      }

      updateMutation.mutate(
        { id, data: updateData },
        {
          onSuccess: () => saveAudienceThenFinish(id, isConference),
          onError: () => toast.error(t("scenarios.saveFailed")),
        },
      );
    }
  };

  const currentTags = form.watch("tags") ?? [];

  const addTag = (tag: string) => {
    if (tag && !currentTags.includes(tag)) {
      form.setValue("tags", [...currentTags, tag]);
    }
  };

  const removeTag = (tag: string) => {
    form.setValue("tags", currentTags.filter((t) => t !== tag));
  };

  const handleAddCustomTag = () => {
    const trimmed = customTagInput.trim();
    if (trimmed) {
      const tagValue = trimmed.includes(":") ? trimmed : `custom:${trimmed}`;
      addTag(tagValue);
      setCustomTagInput("");
    }
  };

  const selectedRubric = rubrics.find((r) => r.id === form.watch("rubric_id"));

  const selectedProfile = profiles.find(
    (p) => p.id === form.watch("hcp_profile_id"),
  );

  const getInitials = (name: string) =>
    name
      ? name
          .split(" ")
          .map((n) => n[0])
          .join("")
          .toUpperCase()
          .slice(0, 2) || "?"
      : "?";

  if (!isNew && scenarioLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/admin/scenarios")}
          >
            <ArrowLeft className="size-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-medium">
              {isNew
                ? t("admin:scenarios.createButton")
                : t("scenarios.editor.editTitle")}
            </h1>
          </div>
        </div>
        <Button
          onClick={form.handleSubmit(handleSubmit)}
          disabled={isArchived || createMutation.isPending || updateMutation.isPending}
        >
          <Save className="size-4 mr-2" />
          {createMutation.isPending || updateMutation.isPending
            ? t("common:saving")
            : t("admin:scenarios.save")}
        </Button>
      </div>

      {/* Archived banner */}
      {isArchived && (
        <div className="flex items-center gap-2 p-3 rounded-md bg-muted border border-border">
          <Info className="size-4 text-muted-foreground shrink-0" />
          <p className="text-sm text-muted-foreground">
            {t("scenarios.editor.archivedBanner")}
          </p>
        </div>
      )}

      {/* Form wraps entire Tabs so state persists across tab switches */}
      <Form {...form}>
        <fieldset disabled={isArchived}>
          <Tabs value={activeTab} onValueChange={handleTabChange}>
            <TabsList className="w-full bg-muted/60 border">
              <TabsTrigger
                value="basic"
                className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                {t("scenarios.editor.tabs.basicInfo")}
              </TabsTrigger>
              <TabsTrigger
                value="linked"
                className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                {t("scenarios.editor.tabs.linkedConfig")}
              </TabsTrigger>
              <TabsTrigger
                value="scoring"
                className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                {t("scenarios.editor.tabs.scoringRules")}
              </TabsTrigger>
            </TabsList>

            {/* Basic Info Tab */}
            <TabsContent value="basic" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-semibold">
                    {t("scenarios.editor.tabs.basicInfo")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t("scenarios.editor.fields.name")}</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t("scenarios.editor.fields.description")}</FormLabel>
                        <FormControl>
                          <Textarea rows={3} {...field} />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <div className="grid grid-cols-2 gap-4">
                    <div className="grid gap-2">
                      <Label>{t("scenarios.editor.fields.mode")}</Label>
                      <div className="flex items-center gap-4">
                        {(["f2f", "conference"] as const).map((m) => (
                          <label key={m} className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              value={m}
                              checked={form.watch("mode") === m}
                              onChange={() => form.setValue("mode", m)}
                              className="accent-primary"
                            />
                            <span className="text-sm uppercase">{m}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                    <div className="grid gap-2">
                      <Label>{t("scenarios.editor.fields.difficulty")}</Label>
                      <div className="flex items-center gap-4">
                        {(["easy", "medium", "hard"] as const).map((d) => (
                          <label key={d} className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              value={d}
                              checked={form.watch("difficulty") === d}
                              onChange={() => form.setValue("difficulty", d)}
                              className="accent-primary"
                            />
                            <span className="text-sm capitalize">{d}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Tags Section */}
                  <div className="grid gap-2">
                    <Label>{t("scenarios.editor.fields.tags")}</Label>

                    {/* Current tags display */}
                    <div className="flex min-h-8 flex-wrap gap-1.5 rounded-md border bg-muted/30 p-2">
                      {currentTags.length === 0 && (
                        <span className="text-xs text-muted-foreground">
                          {t("scenarios.editor.fields.tagsPlaceholder")}
                        </span>
                      )}
                      {currentTags.map((tag) => {
                        const value = tag.includes(":") ? tag.split(":").slice(1).join(":") : tag;
                        return (
                          <Badge
                            key={tag}
                            variant="outline"
                            className="text-xs gap-1 pr-1"
                          >
                            {value}
                            <button
                              type="button"
                              onClick={() => removeTag(tag)}
                              className="ml-0.5 rounded-full hover:bg-destructive/20 p-0.5"
                            >
                              <X className="size-3" />
                            </button>
                          </Badge>
                        );
                      })}
                    </div>

                    {/* Predefined tag categories */}
                    {Object.entries(PREDEFINED_TAGS).map(([category, values]) => (
                      <div key={category} className="flex flex-wrap items-center gap-1.5">
                        <span className="min-w-20 text-xs capitalize text-muted-foreground">
                          {category.replace("_", " ")}:
                        </span>
                        {values.map((value) => {
                          const fullTag = `${category}:${value}`;
                          const isSelected = currentTags.includes(fullTag);
                          return (
                            <button
                              key={fullTag}
                              type="button"
                              onClick={() => isSelected ? removeTag(fullTag) : addTag(fullTag)}
                              className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                                isSelected
                                  ? "bg-primary text-primary-foreground border-primary"
                                  : "bg-background hover:bg-muted border-border"
                              }`}
                            >
                              {value}
                            </button>
                          );
                        })}
                      </div>
                    ))}

                    {/* Custom tag input */}
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder={t("scenarios.editor.fields.tagsPlaceholder")}
                        value={customTagInput}
                        onChange={(e) => setCustomTagInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            handleAddCustomTag();
                          }
                        }}
                        className="flex-1 h-8 text-sm"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleAddCustomTag}
                        className="h-8"
                      >
                        <Plus className="size-3.5" />
                        {t("scenarios.editor.fields.addTag")}
                      </Button>
                    </div>
                  </div>

                  {/* Key Messages */}
                  <ObjectionList
                    items={form.watch("key_messages") ?? []}
                    onChange={(items) => form.setValue("key_messages", items)}
                    label={t("admin:scenarios.keyMessages")}
                    addLabel={t("admin:scenarios.addKeyMessage")}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            {/* Linked Config Tab */}
            <TabsContent value="linked" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-semibold">
                    {t("scenarios.editor.tabs.linkedConfig")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* HCP Profile Selector (F2F only) */}
                  {form.watch("mode") !== "conference" && (
                    <div className="grid gap-2">
                      <Label>{t("scenarios.editor.fields.hcpProfile")}</Label>
                      <Controller
                        control={form.control}
                        name="hcp_profile_id"
                        render={({ field }) => (
                          <Select value={field.value} onValueChange={field.onChange}>
                            <SelectTrigger>
                              <SelectValue placeholder={t("scenarios.editor.fields.selectHcp")}>
                                {selectedProfile && (
                                  <div className="flex items-center gap-2">
                                    <Avatar className="size-5">
                                      <AvatarImage src={selectedProfile.avatar_url} />
                                      <AvatarFallback className="bg-blue-100 text-blue-700 text-[10px]">
                                        {getInitials(selectedProfile.name)}
                                      </AvatarFallback>
                                    </Avatar>
                                    <span>{selectedProfile.name}</span>
                                  </div>
                                )}
                              </SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              {profiles.map((p) => (
                                <SelectItem key={p.id} value={p.id}>
                                  <div className="flex items-center gap-2">
                                    <Avatar className="size-5">
                                      <AvatarImage src={p.avatar_url} />
                                      <AvatarFallback className="bg-blue-100 text-blue-700 text-[10px]">
                                        {getInitials(p.name)}
                                      </AvatarFallback>
                                    </Avatar>
                                    {p.name}
                                  </div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                      />
                      {form.formState.errors.hcp_profile_id && (
                        <p className="text-destructive text-sm">
                          {t("scenarios.editor.fields.hcpProfile")}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Conference Audience (multi-HCP) */}
                  {form.watch("mode") === "conference" && (
                    <ConferenceAudienceConfig
                      value={audience}
                      onChange={setAudience}
                      profiles={profiles}
                      labels={{
                        title: t("scenarios.editor.audience.title"),
                        description: t("scenarios.editor.audience.description", {
                          min: MIN_AUDIENCE,
                          max: MAX_AUDIENCE,
                        }),
                        selectHcp: t("scenarios.editor.audience.selectHcp"),
                        role: t("scenarios.editor.audience.role"),
                        roleAudience: t("scenarios.editor.audience.roleAudience"),
                        roleModerator: t(
                          "scenarios.editor.audience.roleModerator",
                        ),
                        addHcp: t("scenarios.editor.audience.addHcp"),
                        removeHcp: t("scenarios.editor.audience.removeHcp"),
                        moveUp: t("scenarios.editor.audience.moveUp"),
                        moveDown: t("scenarios.editor.audience.moveDown"),
                        primarySpeaker: t("scenarios.editor.audience.primarySpeaker"),
                        secondarySpeaker: t("scenarios.editor.audience.secondarySpeaker"),
                        countHint: t("scenarios.editor.audience.countHint"),
                        minHint: t("scenarios.editor.audience.minHint"),
                        moderatorRequiredHint: t(
                          "scenarios.editor.audience.moderatorRequiredHint",
                        ),
                        duplicateHint: t(
                          "scenarios.editor.audience.duplicateHint",
                        ),
                      }}
                    />
                  )}

                  {form.watch("mode") === "conference" && (
                    <div className="grid gap-5 rounded-md border bg-background p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="grid gap-1">
                          <Label className="font-semibold">
                            {t("scenarios.editor.conferencePrompt.title")}
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            {t("scenarios.editor.conferencePrompt.description")}
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            form.setValue(
                              "conference_prompt_config",
                              DEFAULT_CONFERENCE_PROMPT_CONFIG,
                            )
                          }
                        >
                          {t("scenarios.editor.conferencePrompt.useDefault")}
                        </Button>
                      </div>

                      <div className="grid gap-3 rounded-md border bg-muted/20 p-3">
                        <div className="grid gap-1">
                          <Label>{t("scenarios.editor.conferencePrompt.rulesSection")}</Label>
                          <p className="text-xs text-muted-foreground">
                            {t("scenarios.editor.conferencePrompt.rulesHint")}
                          </p>
                        </div>
                        <Textarea
                          rows={3}
                          className="resize-y bg-background"
                          {...form.register("conference_prompt_config.speaker_order_policy")}
                        />
                      </div>

                      <details className="rounded-md border bg-muted/20 p-3">
                        <summary className="cursor-pointer list-none">
                          <div className="flex items-center justify-between gap-3">
                            <div className="grid gap-1">
                              <Label className="cursor-pointer">
                                {t("scenarios.editor.conferencePrompt.hcpTemplateSection")}
                              </Label>
                              <p className="text-xs text-muted-foreground">
                                {t("scenarios.editor.conferencePrompt.hcpTemplateHint")}
                              </p>
                            </div>
                            <Badge variant="outline" className="shrink-0">
                              {t("scenarios.editor.conferencePrompt.advanced")}
                            </Badge>
                          </div>
                        </summary>
                        <div className="mt-3 grid gap-2">
                          <div className="flex justify-end">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={openAudiencePromptOptimizer}
                              data-testid="optimize-audience-prompt"
                            >
                              <Sparkles className="mr-2 size-3.5" />
                              {t("prompts:actions.optimize", { defaultValue: "AI \u4f18\u5316" })}
                            </Button>
                          </div>
                          <Textarea
                            rows={12}
                            className="font-mono text-xs bg-background"
                            {...form.register("conference_prompt_config.audience_prompt_template")}
                          />
                          <p className="text-xs leading-relaxed text-muted-foreground">
                            {t("scenarios.editor.conferencePrompt.placeholders")}
                          </p>
                        </div>
                      </details>

                      <div className="grid gap-3">
                        <div className="grid gap-1">
                          <Label>{t("scenarios.editor.conferencePrompt.moderatorSection")}</Label>
                          <p className="text-xs text-muted-foreground">
                            {t("scenarios.editor.conferencePrompt.moderatorHint")}
                          </p>
                        </div>
                        {(["invite", "opening", "handoff", "closing"] as const).map((phase) => (
                          <div key={phase} className="grid gap-2 rounded-md border bg-muted/20 p-3">
                            <div className="flex items-center gap-2">
                              <Badge variant="secondary" className="rounded-sm">
                                {t(`scenarios.editor.conferencePrompt.${phase}`)}
                              </Badge>
                            </div>
                            <div className="grid gap-2 md:grid-cols-2">
                              <div className="grid gap-1.5">
                                <span className="text-xs font-medium text-muted-foreground">
                                  {t("scenarios.editor.conferencePrompt.zhLabel")}
                                </span>
                                <Textarea
                                  rows={2}
                                  className="bg-background"
                                  {...form.register(
                                    `conference_prompt_config.moderator_remarks.${phase}.zh`,
                                  )}
                                />
                              </div>
                              <div className="grid gap-1.5">
                                <span className="text-xs font-medium text-muted-foreground">
                                  {t("scenarios.editor.conferencePrompt.enLabel")}
                                </span>
                                <Textarea
                                  rows={2}
                                  className="bg-background"
                                  {...form.register(
                                    `conference_prompt_config.moderator_remarks.${phase}.en`,
                                  )}
                                />
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Skill Selector */}
                  <div className="grid gap-2">
                    <Label>{t("scenarios.editor.fields.skill")}</Label>
                    <Controller
                      control={form.control}
                      name="skill_id"
                      render={({ field }) => (
                        <Select value={field.value} onValueChange={field.onChange}>
                          <SelectTrigger>
                            <SelectValue placeholder={t("scenarios.editor.fields.selectSkill")} />
                          </SelectTrigger>
                          <SelectContent>
                            {publishedSkills.map((s) => (
                              <SelectItem key={s.id} value={s.id}>
                                <div className="flex items-center gap-2">
                                  <span>{s.name}</span>
                                  <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                                    v{s.current_version}
                                  </span>
                                  {s.quality_score != null && (
                                    <span className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                                      Q:{s.quality_score}
                                    </span>
                                  )}
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                    {form.formState.errors.skill_id && (
                      <p className="text-destructive text-sm">
                        {form.formState.errors.skill_id.message}
                      </p>
                    )}
                    {publishedSkills.length === 0 && (
                      <p className="text-sm text-destructive">
                        {t("scenarios.editor.fields.noPublishedSkills")}
                      </p>
                    )}
                    {scenario?.skill_id && scenario.skill_id === form.watch("skill_id") && (
                      <SkillStatusBadge skillId={scenario.skill_id} />
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Scoring Rules Tab */}
            <TabsContent value="scoring" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-semibold">
                    {t("scenarios.editor.tabs.scoringRules")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Rubric Selector */}
                  <div className="grid gap-2">
                    <Label>{t("admin:scenarios.scoringRubric")} *</Label>
                    <Controller
                      control={form.control}
                      name="rubric_id"
                      render={({ field }) => (
                        <Select
                          value={field.value ?? ""}
                          onValueChange={field.onChange}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder={t("admin:scenarios.selectRubric")} />
                          </SelectTrigger>
                          <SelectContent>
                            {rubrics
                              .sort((a, b) => (b.is_default ? 1 : 0) - (a.is_default ? 1 : 0))
                              .map((r) => (
                                <SelectItem key={r.id} value={r.id}>
                                  {r.name} {r.is_default ? t("admin:scenarios.rubricDefault") : ""}
                                  ({t("admin:scenarios.dimensionCount", { count: r.dimensions.length })})
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                    {form.formState.errors.rubric_id && (
                      <p className="text-destructive text-sm">
                        {t("admin:scenarios.rubricRequired")}
                      </p>
                    )}
                  </div>

                  {/* Rubric Dimension Preview */}
                  {selectedRubric ? (
                    <Card className="bg-muted/50">
                      <CardContent className="p-4 space-y-2">
                        {selectedRubric.dimensions.map((dim) => (
                          <div key={dim.name} className="flex items-center justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between">
                                <span className="text-sm font-medium truncate">{dim.name}</span>
                                <span className="text-sm text-muted-foreground ml-2">{dim.weight}%</span>
                              </div>
                              <div className="h-1.5 bg-muted rounded-full mt-1">
                                <div
                                  className="h-full bg-primary rounded-full"
                                  style={{ width: `${dim.weight}%` }}
                                />
                              </div>
                              {dim.criteria.length > 0 && (
                                <p className="text-xs text-muted-foreground truncate mt-0.5">
                                  {dim.criteria.join("; ")}
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {t("admin:scenarios.dimensionPreviewEmpty")}
                    </p>
                  )}

                  {/* Manage Rubrics link */}
                  <button
                    type="button"
                    className="text-sm text-primary hover:underline cursor-pointer"
                    onClick={() => navigate("/admin/scoring-rubrics")}
                  >
                    {t("admin:scenarios.manageRubrics")}
                  </button>

                  {/* Pass Threshold */}
                  <div className="grid gap-2">
                    <Label>{t("admin:scenarios.passThreshold")}</Label>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      {...form.register("pass_threshold", { valueAsNumber: true })}
                      className="w-32"
                    />
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </fieldset>
      </Form>
    </div>
  );
}

/** Inline badge that warns when skill is archived. */
function SkillStatusBadge({ skillId }: { skillId: string }) {
  const { t } = useTranslation("admin");
  const { data: skillsData } = usePublishedSkills();
  const allSkills = skillsData?.items ?? [];
  const skill = allSkills.find((s) => s.id === skillId);
  if (skill) {
    return null;
  }
  return (
    <div className="flex items-center gap-1 text-xs text-warning">
      <AlertTriangle className="size-3" />
      <span>{t("scenarios.editor.fields.skillArchived")}</span>
    </div>
  );
}
