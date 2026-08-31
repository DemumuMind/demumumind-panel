<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import { fetchUsage } from '$lib/api';
	import { showToast } from '$lib/stores';

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

<h1 class="text-2xl font-bold mb-6">Usage</h1>

<p class="text-sm text-zinc-500 mb-4">Total records: {total}</p>

<Card>
	{#if items.length === 0}
		<p class="text-center text-zinc-500 py-8">No usage data yet</p>
	{:else}
		<div class="space-y-4">
			{#each items as u}
				<div>
					<div class="flex justify-between text-sm mb-1">
						<span class="font-medium">{u.agent_type}</span>
						<span class="text-zinc-400">${u.cost_usd.toFixed(4)}</span>
					</div>
					<div class="flex gap-4 text-xs text-zinc-500 mb-1">
						<span>{u.requests} requests</span>
						<span>{u.tokens_in} in / {u.tokens_out} out</span>
					</div>
					<div class="h-2 bg-zinc-800 rounded-full overflow-hidden">
						<div
							class="h-full bg-indigo-600 rounded-full transition-all"
							style="width: {((u.tokens_in + u.tokens_out) / maxTokens * 100).toFixed(1)}%"
						></div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</Card>