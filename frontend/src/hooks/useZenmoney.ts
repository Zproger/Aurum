import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchZenmoneyStatus, syncZenmoney } from "@/api/zenmoney";

export function useZenmoneyStatus() {
  return useQuery({
    queryKey: ["zenmoney", "status"],
    queryFn: fetchZenmoneyStatus,
  });
}

export function useSyncZenmoney() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (forceFull: boolean = false) => syncZenmoney(forceFull),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zenmoney", "status"] });
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["cashFlow"] });
      queryClient.invalidateQueries({ queryKey: ["netWorth"] });
      queryClient.invalidateQueries({ queryKey: ["budgets"] });
    },
  });
}
