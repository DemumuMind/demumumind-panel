<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/components/ui/card.svelte';
	import Badge from '$lib/components/ui/badge.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import { fetchPlugins, uploadPlugin, invokePlugin } from '$lib/api';
	import { showToast } from '$lib/stores';

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

<h1 class="text-2xl font-bold mb-6">Plugins</h1>

<Card class="mb-6">
	<h2 class="text-sm font-semibold mb-3">Upload .wasm Plugin</h2>
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
		<Input placeholder="Plugin name" bind:value={pluginName} />
		<Input placeholder="Ed25519 signature (hex)" bind:value={pluginSignature} />
		<input type="file" accept=".wasm" onchange={(e) => (file = (e.target as HTMLInputElement).files?.[0])} class="text-sm text-zinc-400 file:mr-3 file:rounded file:border-0 file:bg-zinc-800 file:px-3 file:py-1 file:text-sm file:text-zinc-200" />
	</div>
	<Button onclick={upload} disabled={busy || !file || !pluginName} class="mt-3">Upload</Button>
</Card>

<Card>
	<div class="overflow-x-auto">
	<table class="w-full text-sm min-w-[480px]">
		<thead>
			<tr class="text-left text-zinc-400 border-b border-zinc-800">
				<th class="py-2">Name</th>
				<th>Size</th>
				<th>Signature</th>
				<th>Status</th>
				<th>Invoke</th>
			</tr>
		</thead>
		<tbody>
			{#each plugins as p}
				<tr class="border-b border-zinc-800/50">
					<td class="py-2 font-medium">{p.name}</td>
					<td class="text-zinc-400">{p.size_bytes} B</td>
					<td>
						<Badge variant={p.signature_valid ? 'success' : 'danger'}>{p.signature_valid ? 'valid' : 'invalid'}</Badge>
					</td>
					<td>
						<Badge variant={p.loaded ? 'success' : 'danger'}>{p.loaded ? 'loaded' : 'error'}</Badge>
						{#if p.error}
							<span class="text-xs text-red-400 ml-2">{p.error}</span>
						{/if}
					</td>
					<td class="py-2">
						<div class="flex items-center gap-2">
							<Input placeholder="fn" bind:value={invokeFn} class="w-20" />
							<Input placeholder="[2, 3]" bind:value={invokeArgs} class="w-24" />
							<Button onclick={() => invoke(p.name)} class="!px-2 !py-1 !text-xs">Invoke</Button>
						</div>
						{#if invokeResult[p.name]}
							<pre class="mt-1 text-xs text-zinc-400 whitespace-pre-wrap">{invokeResult[p.name]}</pre>
						{/if}
					</td>
				</tr>
			{/each}
			{#if plugins.length === 0}
				<tr><td colspan="5" class="py-4 text-center text-zinc-500">No plugins uploaded</td></tr>
			{/if}
		</tbody>
	</table>
	</div>
</Card>