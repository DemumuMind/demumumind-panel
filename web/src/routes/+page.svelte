<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Stat from '$lib/components/ui/stat.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import { getJSON, health, fetchUsage, fetchUsageTimeseries, fetchMcpServers, fetchPlugins, runCleanup } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Bot, Boxes, Key, Cable, Puzzle, Activity, ArrowUpRight, Trash2 } from 'lucide-svelte';

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

	let maxTsTokens = $derived(Math.max(...ts.map((p) => (p.tokens_in || 0) + (p.tokens_out || 0)), 1));
	let totalRequests = $derived(ts.reduce((a, p) => a + (p.requests || 0), 0));
	let maxBar = $derived(Math.max(...usage.map((u) => u.tokens_in + u.tokens_out), 1));

	async function doCleanup() {
		try {
			const r = await runCleanup();
			showToast(
				`Cleanup: ${r.providers_deactivated} prov, ${r.models_deactivated} models, ${r.usage_deleted} usage rows`,
				'success'
			);
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}
</script>

<h1 class="text-2xl font-bold mb-6 flex items-center gap-2 text-(--text)">
	<Activity class="w-5 h-5 text-(--accent)" />
	Dashboard
</h1>

{#if loading}
	<p class="text-(--text-faint) text-sm">Loading…</p>
{:else}
	{#if h}
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
			<Card class="flex-1">
				<div class="text-sm text-(--text-muted)">Status</div>
				<div class="text-lg font-semibold mt-1">
					<Badge variant={h.status === 'ok' ? 'success' : 'danger'} dot>{h.status}</Badge>
				</div>
			</Card>
			<Card class="flex-1">
				<div class="text-sm text-(--text-muted)">Version</div>
				<div class="text-lg font-semibold mt-1 tabular-nums">{h.version}</div>
			</Card>
			<Card class="flex-1">
				<div class="text-sm text-(--text-muted)">DB</div>
				<div class="text-lg font-semibold mt-1">
					<Badge variant={h.checks.db === 'ok' ? 'success' : 'danger'} dot>{h.checks.db}</Badge>
				</div>
			</Card>
			<Card class="flex-1">
				<div class="text-sm text-(--text-muted)">Redis</div>
				<div class="text-lg font-semibold mt-1">
					<Badge variant={h.checks.redis === 'ok' ? 'success' : 'warning'} dot>{h.checks.redis}</Badge>
				</div>
			</Card>
		</div>
	{/if}

	<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
		<Stat label="Providers" value={providers}><Bot class="w-4 h-4 text-(--accent)" /></Stat>
		<Stat label="Models" value={models}><Boxes class="w-4 h-4 text-(--accent)" /></Stat>
		<Stat label="API Keys" value={keys}><Key class="w-4 h-4 text-(--accent)" /></Stat>
		<Stat label="MCP Servers" value={mcpServers}><Cable class="w-4 h-4 text-(--accent)" /></Stat>
		<Stat label="Plugins" value={plugins}><Puzzle class="w-4 h-4 text-(--accent)" /></Stat>
		<Stat label="Requests (14d)" value={totalRequests}><ArrowUpRight class="w-4 h-4 text-(--accent)" /></Stat>
	</div>

	<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
		<Card>
			<h2 class="text-sm font-semibold mb-3 text-(--text)">Tokens by day (14d)</h2>
			{#if ts.length === 0}
				<p class="text-center text-(--text-faint) text-sm py-6">No usage data yet</p>
			{:else}
				<div class="flex items-end gap-1 h-40">
					{#each ts as p}
						<div class="flex-1 flex flex-col items-center gap-1" title={`${p.date}: ${p.tokens_in} in / ${p.tokens_out} out`}>
							<div class="w-full flex flex-col justify-end rounded bg-(--bg-elevated) overflow-hidden" style="height: {((p.tokens_in || 0) + (p.tokens_out || 0)) / maxTsTokens * 100}%">
								<div class="w-full bg-gradient-to-t from-(--accent) to-(--accent-2)" style="height: {((p.tokens_in || 0) / ((p.tokens_in || 0) + (p.tokens_out || 0) || 1)) * 100}%"></div>
								<div class="w-full bg-emerald-500" style="height: {((p.tokens_out || 0) / ((p.tokens_in || 0) + (p.tokens_out || 0) || 1)) * 100}%"></div>
							</div>
						</div>
					{/each}
				</div>
				<div class="flex gap-4 mt-2 text-xs text-(--text-faint)">
					<span class="flex items-center gap-1"><span class="w-2 h-2 rounded bg-(--accent) inline-block"></span> in</span>
					<span class="flex items-center gap-1"><span class="w-2 h-2 rounded bg-emerald-500 inline-block"></span> out</span>
					<span class="ml-auto tabular-nums">{ts[0]?.date} … {ts[ts.length - 1]?.date}</span>
				</div>
			{/if}
		</Card>

		<Card>
			<h2 class="text-sm font-semibold mb-3 text-(--text)">Usage by agent</h2>
			{#if usage.length === 0}
				<p class="text-center text-(--text-faint) text-sm py-6">No usage data yet</p>
			{:else}
				<div class="space-y-4">
					{#each usage as u}
						<div>
							<div class="flex justify-between text-sm mb-1">
								<span class="font-medium text-(--text)">{u.agent_type}</span>
								<span class="text-(--text-muted) tabular-nums">${u.cost_usd.toFixed(4)}</span>
							</div>
							<div class="flex gap-4 text-xs text-(--text-faint) mb-1">
								<span>{u.requests} req</span>
								<span class="tabular-nums">{u.tokens_in} in / {u.tokens_out} out</span>
							</div>
							<div class="h-2 bg-(--bg-elevated) rounded-full overflow-hidden">
								<div
									class="h-full bg-gradient-to-r from-(--accent) to-(--accent-2) rounded-full transition-all duration-500"
									style="width: {Math.min((u.tokens_in + u.tokens_out) / maxBar * 100, 100)}%"
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
			<div class="flex items-center justify-between mb-2">
				<h2 class="text-sm font-semibold text-(--text)">Health Checks</h2>
				<button
					onclick={doCleanup}
					class="flex items-center gap-1 rounded-md border border-(--border) bg-(--bg-elevated) px-2 py-1 text-xs text-(--text-muted) hover:text-(--text) hover:border-(--border-strong) transition-colors"
					title="Deactivate dead providers, delete old usage"
				>
					<Trash2 class="w-3 h-3" /> Run cleanup
				</button>
			</div>
			<table class="w-full text-sm">
				<thead>
					<tr class="text-left text-(--text-muted) border-b border-(--border)">
						<th class="py-2 font-medium">Component</th>
						<th>Status</th>
					</tr>
				</thead>
				<tbody>
					{#each Object.entries(h.checks) as [component, status]}
						<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover)">
							<td class="py-2 text-(--text)">{component}</td>
							<td>
								<Badge variant={status === 'ok' ? 'success' : status === 'fallback' ? 'warning' : 'danger'} dot>{status}</Badge>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</Card>
	{/if}
{/if}