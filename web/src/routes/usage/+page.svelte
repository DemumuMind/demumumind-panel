<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import Stat from '$lib/components/ui/stat.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchUsage, fetchUsageByProvider } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { BarChart3, DollarSign, Sparkles, HelpCircle, Database, Infinity } from 'lucide-svelte';

	let items = $state<any[]>([]);
	let providerItems = $state<any[]>([]);
	let total = $state(0);

	let totals = $derived({
		totalCost: items.reduce((s, i) => s + i.cost_usd, 0),
		totalRequests: items.reduce((s, i) => s + i.requests, 0),
		totalFree: items.reduce((s, i) => s + i.free_requests, 0),
		totalUnknown: items.reduce((s, i) => s + i.unknown_requests, 0),
		totalCached: items.reduce((s, i) => s + i.cached_requests, 0)
	});

	onMount(async () => {
		try {
			const [data, provData] = await Promise.all([
				fetchUsage(100, 0),
				fetchUsageByProvider(100, 0)
			]);
			items = data.items;
			providerItems = provData.items;
			total = data.total;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	});

	let maxTokens = $derived(Math.max(...items.map((i) => i.tokens_in + i.tokens_out), 1));
	let maxProvTokens = $derived(Math.max(...providerItems.map((i) => i.tokens_in + i.tokens_out), 1));

	function fmtCost(u: any): { text: string; cls: string; title: string } {
		if (u.requests === 0) return { text: '—', cls: 'text-(--text-faint)', title: 'No requests' };
		if (u.unknown_requests === u.requests) {
			return { text: '—', cls: 'text-(--text-faint)', title: 'Cost not disclosed by provider' };
		}
		if (u.free_requests === u.requests) {
			return { text: 'Free', cls: 'text-emerald-400', title: 'All requests were free / unlimited' };
		}
		if (u.cost_usd > 0.000001) {
			return { text: `$${u.cost_usd.toFixed(6)}`, cls: 'tabular-nums', title: `Total cost: $${u.cost_usd.toFixed(6)}` };
		}
		// mixed: free + unknown, zero cost
		return { text: 'Free/—', cls: 'text-(--text-faint)', title: 'Free + cost unknown' };
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<BarChart3 class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Usage</h1>
</div>

<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
	<Stat label="Total cost" value={totals.totalCost > 0.000001 ? `$${totals.totalCost.toFixed(4)}` : '$0.00'}>
		<DollarSign class="w-4 h-4" />
	</Stat>
	<Stat label="Total requests" value={totals.totalRequests}>
		<BarChart3 class="w-4 h-4" />
	</Stat>
	<Stat label="Free requests" value={totals.totalFree}>
		<Sparkles class="w-4 h-4" />
	</Stat>
	<Stat label="Cached" value={totals.totalCached}>
		<Database class="w-4 h-4" />
	</Stat>
</div>

<p class="text-sm text-(--text-muted) mb-4">Total records: {total} {totals.totalUnknown > 0 ? `(${totals.totalUnknown} with unknown pricing)` : ''}</p>

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
						<span class={fmtCost(u).cls}>
							{fmtCost(u).text}
							{#if u.cached_requests > 0 && u.cached_requests < u.requests}
								<Badge variant="info" class="ml-1">cached {u.cached_requests}</Badge>
							{/if}
							{#if u.free_requests > 0 && u.free_requests < u.requests && u.cost_usd > 0}
								<Badge variant="success" class="ml-1">free {u.free_requests}</Badge>
							{/if}
						</span>
					</div>
					<div class="flex gap-4 text-xs text-(--text-faint) mb-1 tabular-nums">
						<span>{u.requests} requests</span>
						<span>{u.tokens_in} in / {u.tokens_out} out</span>
						{#if u.cached_requests > 0}
							<Badge variant="info" dot>cached</Badge>
						{/if}
						{#if u.free_requests === u.requests}
							<Badge variant="success" dot>Free</Badge>
						{/if}
						{#if u.unknown_requests > 0 && u.unknown_requests === u.requests}
							<Badge variant="warning" dot>Cost unknown</Badge>
						{/if}
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

<Card class="mt-4">
	<h2 class="text-sm font-semibold mb-3 text-(--text)">Usage by provider</h2>
	{#if providerItems.length === 0}
		<EmptyState title="No usage by provider yet" description="Send some requests and provider usage will show up here.">
			{#snippet icon()}<BarChart3 class="w-5 h-5" />{/snippet}
		</EmptyState>
	{:else}
		<div class="space-y-5">
			{#each providerItems as u}
				<div>
					<div class="flex justify-between text-sm mb-1">
						<span class="font-medium text-(--text)">{u.agent_type}</span>
						<span class={fmtCost(u).cls}>
							{fmtCost(u).text}
							{#if u.cached_requests > 0 && u.cached_requests < u.requests}
								<Badge variant="info" class="ml-1">cached {u.cached_requests}</Badge>
							{/if}
							{#if u.free_requests > 0 && u.free_requests < u.requests && u.cost_usd > 0}
								<Badge variant="success" class="ml-1">free {u.free_requests}</Badge>
							{/if}
						</span>
					</div>
					<div class="flex gap-4 text-xs text-(--text-faint) mb-1 tabular-nums">
						<span>{u.requests} requests</span>
						<span>{u.tokens_in} in / {u.tokens_out} out</span>
						{#if u.cached_requests > 0}
							<Badge variant="info" dot>cached</Badge>
						{/if}
						{#if u.free_requests === u.requests}
							<Badge variant="success" dot>Free</Badge>
						{/if}
						{#if u.unknown_requests > 0 && u.unknown_requests === u.requests}
							<Badge variant="warning" dot>Cost unknown</Badge>
						{/if}
					</div>
					<div class="h-2 bg-(--bg-elevated) rounded-full overflow-hidden">
						<div
							class="h-full bg-gradient-to-r from-(--accent) to-(--accent-2) rounded-full transition-all duration-500"
							style="width: {((u.tokens_in + u.tokens_out) / maxProvTokens * 100).toFixed(1)}%"
						></div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</Card>