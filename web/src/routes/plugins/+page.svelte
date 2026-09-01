<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import Table from '$lib/components/ui/table.svelte';
	import EmptyState from '$lib/components/ui/empty-state.svelte';
	import { fetchPlugins, uploadPlugin, invokePlugin } from '$lib/api';
	import { showToast } from '$lib/stores';
	import { Puzzle, Upload, Zap } from 'lucide-svelte';

	let plugins = $state<any[]>([]);
	let pluginName = $state('');
	let pluginSignature = $state('');
	let file: File | undefined = $state();
	let busy = $state(false);
	let invokeFn = $state('add');
	let invokeArgs = $state('[2, 3]');
	let invokeResult = $state<Record<string, string>>({});

	async function load() {
		try {
			plugins = await fetchPlugins();
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	}
	onMount(load);

	async function upload() {
		if (!file || !pluginName) return;
		busy = true;
		try {
			await uploadPlugin(pluginName, pluginSignature, file);
			showToast('Plugin uploaded', 'success');
			pluginName = pluginSignature = '';
			file = undefined;
			await load();
		} catch (e: any) {
			showToast(e.message, 'error');
		} finally {
			busy = false;
		}
	}

	async function invoke(pname: string) {
		try {
			const args = JSON.parse(invokeArgs);
			invokeResult[pname] = 'invoking…';
			const r = await invokePlugin(pname, invokeFn, args);
			invokeResult[pname] = JSON.stringify(r, null, 2);
		} catch (e: any) {
			invokeResult[pname] = `Error: ${e.message}`;
		}
	}
</script>

<div class="flex items-center gap-2 mb-6">
	<Puzzle class="w-5 h-5 text-(--accent)" />
	<h1 class="text-2xl font-bold text-(--text)">Plugins</h1>
</div>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3 text-(--text)">Upload .wasm Plugin</h2>
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
		<Input placeholder="Plugin name" bind:value={pluginName} />
		<Input placeholder="Ed25519 signature (hex)" bind:value={pluginSignature} />
		<input type="file" accept=".wasm" onchange={(e) => (file = (e.target as HTMLInputElement).files?.[0])} class="text-sm text-(--text-muted) file:mr-3 file:rounded file:border-0 file:bg-(--bg-elevated) file:px-3 file:py-1 file:text-sm file:text-(--text)" />
	</div>
	<Button onclick={upload} disabled={busy || !file || !pluginName} class="mt-3"><Upload class="w-4 h-4" /> Upload</Button>
</Card>

<Card>
	<Table headers={['Name', 'Size', 'Signature', 'Status', 'Invoke']}>
		{#each plugins as p}
			<tr class="border-b border-(--border)/50 hover:bg-(--bg-hover) transition-colors">
				<td class="py-2 px-3 font-medium text-(--text)">{p.name}</td>
				<td class="py-2 px-3 text-(--text-muted) tabular-nums">{p.size_bytes} B</td>
				<td class="py-2 px-3">
					<Badge variant={p.signature_valid ? 'success' : 'danger'} dot>{p.signature_valid ? 'valid' : 'invalid'}</Badge>
				</td>
				<td class="py-2 px-3">
					<Badge variant={p.loaded ? 'success' : 'danger'}>{p.loaded ? 'loaded' : 'error'}</Badge>
					{#if p.error}
						<span class="text-xs text-red-400 ml-2">{p.error}</span>
					{/if}
				</td>
				<td class="py-2 px-3">
					<div class="flex items-center gap-2">
						<Input placeholder="fn" bind:value={invokeFn} class="w-20" />
						<Input placeholder="[2, 3]" bind:value={invokeArgs} class="w-24" />
						<Button variant="secondary" size="sm" onclick={() => invoke(p.name)}><Zap class="w-3.5 h-3.5" /></Button>
					</div>
					{#if invokeResult[p.name]}
						<pre class="mt-1 text-xs text-(--text-muted) whitespace-pre-wrap">{invokeResult[p.name]}</pre>
					{/if}
				</td>
			</tr>
		{/each}
	</Table>
	{#if plugins.length === 0}
		<EmptyState title="No plugins uploaded" description="Upload a .wasm plugin with its Ed25519 signature.">
			{#snippet icon()}<Puzzle class="w-5 h-5" />{/snippet}
		</EmptyState>
	{/if}
</Card>
