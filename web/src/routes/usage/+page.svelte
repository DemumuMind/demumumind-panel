<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchUsage } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { BarChart3 } from 'lucide-svelte';

	let items = $state<any[]>([]);
	let total = $state(0);

	onMount(async () => {
		try {
			const data = await fetchUsage(100, 0);
			items = data.items;
			total = data.total;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	});

	let maxTokens = $derived(Math.max(...items.map((i) => i.tokens_in + i.tokens_out), 1));
</script>

<div class="flex items-center gap-2 mb-6">
	<BarChart3 class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Usage</h1>
</div>

<p class="text-sm text-(--text-muted) mb-4">Total records: {total}</p>

<Card>
	{#if items.length === 0}
		<EmptyState title="No usage data yet" description="Send some requests and the usage will show up here.">
			{#snippet icon()}<BarChart3 class="w-5 h-5" />{/snippet}
		</EmptyState>
	{:else}
		<div class="space-y-5">
			{#each items as u}
				<div>
					<div class="flex justify-between text-sm mb-1">
						<span class="font-medium text-(--text)">{u.agent_type}</span>
						<span class="text-(--text-muted) tabular-nums">${u.cost_usd.toFixed(4)}</span>
					</div>
					<div class="flex gap-4 text-xs text-(--text-faint) mb-1 tabular-nums">
						<span>{u.requests} requests</span>
						<span>{u.tokens_in} in / {u.tokens_out} out</span>
					</div>
					<div class="h-2 bg-(--bg-elevated) rounded-full overflow-hidden">
						<div
							class="h-full bg-gradient-to-r from-(--accent) to-(--accent-2) rounded-full transition-all duration-500"
							style="width: {((u.tokens_in + u.tokens_out) / maxTokens * 100).toFixed(1)}%"
						></div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</Card>
