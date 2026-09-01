<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import { getJSON, health, fetchUsage, fetchUsageTimeseries, fetchMcpServers, fetchPlugins } from '$lib/api';
	import { showToast } from '$lib/stores';

	let h = $state<any>(null);
	let providers = $state(0);
	let models = $state(0);
	let keys = $state(0);
	let mcpServers = $state(0);
	let plugins = $state(0);
	let usage = $state<any[]>([]);
	let ts = $state<any[]>([]);
	let loading = $state(true);

	onMount(async () => {
		try {
			h = await health();
		} catch { h = null; }
		try {
			providers = (await getJSON<any>('/v1/admin/providers?limit=1').catch(() => ({ total: 0 }))).total || 0;
			models = (await getJSON<any>('/v1/admin/models?limit=1').catch(() => ({ total: 0 }))).total || 0;
			keys = (await getJSON<any>('/v1/admin/keys?limit=1').catch(() => ({ total: 0 }))).total || 0;
			mcpServers = (await fetchMcpServers(1, 0).catch(() => ({ total: 0 }))).total || 0;
			plugins = (await fetchPlugins().catch(() => [])).length || 0;
			usage = (await fetchUsage(5, 0).catch(() => ({ items: [] }))).items || [];
			ts = (await fetchUsageTimeseries(14).catch(() => [])) ?? [];
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			loading = false;
		}
	});

	let maxTsTokens = $derived(
		Math.max(...ts.map((p) => (p.tokens_in || 0) + (p.tokens_out || 0)), 1)
	);
	let totalRequests = $derived(ts.reduce((a, p) => a + (p.requests || 0), 0));
</script>

<h1 class="text-2xl font-bold mb-6">Dashboard</h1>

{#if loading}
	<p class="text-zinc-500 text-sm">Loading…</p>
{:else}
	{#if h}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
			<Card class="flex-1">
				<div class="text-sm text-zinc-400">Status</div>
				<div class="text-lg font-semibold mt-1">
					<Badge variant={h.status === 'ok' ? 'success' : 'danger'}>{h.status}</Badge>
				</div>
			</Card>
			<Card class="flex-1">
				<div class="text-sm text-zinc-400">Version</div>
				<div class="text-lg font-semibold mt-1">{h.version}</div>
			</Card>
			<Card class="flex-1">
				<div class="text-sm text-zinc-400">DB</div>
				<div class="text-lg font-semibold mt-1">
					<Badge variant={h.checks.db === 'ok' ? 'success' : 'danger'}>{h.checks.db}</Badge>
				</div>
			</Card>
			<Card class="flex-1">
				<div class="text-sm text-zinc-400">Redis</div>
				<div class="text-lg font-semibold mt-1">
					<Badge variant={h.checks.redis === 'ok' ? 'success' : 'warning'}>{h.checks.redis}</Badge>
				</div>
			</Card>
		</div>
	{/if}

	<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
		<Card>
			<div class="text-2xl font-bold">{providers}</div>
			<div class="text-sm text-zinc-400">Providers</div>
		</Card>
		<Card>
			<div class="text-2xl font-bold">{models}</div>
			<div class="text-sm text-zinc-400">Models</div>
		</Card>
		<Card>
			<div class="text-2xl font-bold">{keys}</div>
			<div class="text-sm text-zinc-400">API Keys</div>
		</Card>
		<Card>
			<div class="text-2xl font-bold">{mcpServers}</div>
			<div class="text-sm text-zinc-400">MCP Servers</div>
		</Card>
		<Card>
			<div class="text-2xl font-bold">{plugins}</div>
			<div class="text-sm text-zinc-400">Plugins</div>
		</Card>
		<Card>
			<div class="text-2xl font-bold">{totalRequests}</div>
			<div class="text-sm text-zinc-400">Requests (14d)</div>
		</Card>
	</div>

	<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
		<Card>
			<h2 class="text-sm font-semibold mb-3">Tokens by day (14d)</h2>
			{#if ts.length === 0}
				<p class="text-center text-zinc-600 text-sm py-6">No usage data yet</p>
			{:else}
				<div class="flex items-end gap-1 h-40">
					{#each ts as p}
						<div class="flex-1 flex flex-col items-center gap-1" title={`${p.date}: ${p.tokens_in} in / ${p.tokens_out} out`}>
							<div class="w-full flex flex-col justify-end rounded bg-zinc-800 overflow-hidden" style="height: {((p.tokens_in || 0) + (p.tokens_out || 0)) / maxTsTokens * 100}%">
								<div class="w-full bg-indigo-600" style="height: {((p.tokens_in || 0) / ((p.tokens_in || 0) + (p.tokens_out || 0) || 1)) * 100}%"></div>
								<div class="w-full bg-emerald-600" style="height: {((p.tokens_out || 0) / ((p.tokens_in || 0) + (p.tokens_out || 0) || 1)) * 100}%"></div>
							</div>
						</div>
					{/each}
				</div>
				<div class="flex gap-4 mt-2 text-xs text-zinc-500">
					<span class="flex items-center gap-1"><span class="w-2 h-2 rounded bg-indigo-600 inline-block"></span> in</span>
					<span class="flex items-center gap-1"><span class="w-2 h-2 rounded bg-emerald-600 inline-block"></span> out</span>
					<span class="ml-auto">{ts[0]?.date} … {ts[ts.length - 1]?.date}</span>
				</div>
			{/if}
		</Card>

		<Card>
			<h2 class="text-sm font-semibold mb-3">Usage by agent</h2>
			{#if usage.length === 0}
				<p class="text-center text-zinc-600 text-sm py-6">No usage data yet</p>
			{:else}
				<div class="space-y-4">
					{#each usage as u}
						<div>
							<div class="flex justify-between text-sm mb-1">
								<span class="font-medium">{u.agent_type}</span>
								<span class="text-zinc-400">${u.cost_usd.toFixed(4)}</span>
							</div>
							<div class="flex gap-4 text-xs text-zinc-500 mb-1">
								<span>{u.requests} req</span>
								<span>{u.tokens_in} in / {u.tokens_out} out</span>
							</div>
							<div class="h-2 bg-zinc-800 rounded-full overflow-hidden">
								<div
									class="h-full bg-indigo-600 rounded-full transition-all"
									style="width: {Math.min((u.tokens_in + u.tokens_out) / maxTsTokens * 100, 100)}%"
								></div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card>
	</div>

	{#if h}
		<Card>
			<h2 class="text-sm font-semibold mb-2">Health Checks</h2>
			<table class="w-full text-sm">
				<thead>
					<tr class="text-left text-zinc-400 border-b border-zinc-800">
						<th class="py-2">Component</th>
						<th>Status</th>
					</tr>
				</thead>
				<tbody>
					{#each Object.entries(h.checks) as [component, status]}
						<tr class="border-b border-zinc-800/50">
							<td class="py-2">{component}</td>
							<td>
								<Badge variant={status === 'ok' ? 'success' : status === 'fallback' ? 'warning' : 'danger'}>{status}</Badge>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</Card>
	{/if}
{/if}