import { useQuery } from "@tanstack/react-query";
import { fetchAgentFoundationModels } from "@/api/agent-foundation-models";

const QUERY_KEY = "agent-foundation-models";

export function useAgentFoundationModels() {
  return useQuery({
    queryKey: [QUERY_KEY],
    queryFn: fetchAgentFoundationModels,
    staleTime: 5 * 60 * 1000,
  });
}
