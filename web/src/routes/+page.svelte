<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import { getJSON, health } from '$lib/api';

	let h = $state<any>(null);
	let providers = $state(0);
	let models = $state(0);
	let keys = $state(0);

	onMount(async () => {
		try {
			h = await health();
			const [pr, mo, ke] = await Promise.all([
				getJSON<any>('/v1/admin/providers?limit=1').catch(() => ({ total: 0 })),
				getJSON<any>('/v1/admin/models?limit=1').catch(() => ({ total: 0 })),
				getJSON<any>('/v1/admin/keys?limit=1').catch(() => ({ total: 0 }))
			]);
			providers = pr.total;
			models = mo.total;
			keys = ke.total;
		} catch {}
	});
</script>

<h1 class="text-2xl font-bold mb-6">Dashboard</h1>

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
				<Badge variant={h.checks.redis === 'ok' ? 'success' : 'danger'}>{h.checks.redis}</Badge>
			</div>
		</Card>
	</div>
{/if}

<div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
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
</div>

{#if h}
	<Card>
		<h2 class="text-sm font-semibold mb-2">Health Checks</h2>
		<pre class="text-xs text-zinc-400">{JSON.stringify(h.checks, null, 2)}</pre>
	</Card>
{/if}