<script lang="ts">
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import { getJSON, postJSON } from '$lib/api';
	import { showToast, panelKey } from '$lib/stores';
	import { get } from 'svelte/store';

	let serverName = $state('');
	let toolName = $state('');
	let method = $state('tools/list');
	let params = $state('{}');
	let result = $state('');

	async function call() {
		if (!get(panelKey)) {
			showToast('Login first', 'error');
			return;
		}
		result = '';
		let parsed: any;
		try {
			parsed = JSON.parse(params);
		} catch {
			showToast('Invalid JSON in params', 'error');
			return;
		}
		try {
			const p = { server: serverName, tool: toolName, ...parsed };
			const r = await postJSON<any>('/mcp', {
				jsonrpc: '2.0',
				id: '1',
				method,
				params: p
			});
			result = JSON.stringify(r, null, 2);
		} catch (e: any) {
			result = `Error: ${e.message}`;
		}
	}
</script>

<h1 class="text-2xl font-bold mb-6">MCP</h1>

<p class="text-sm text-zinc-500 mb-4">JSON-RPC 2.0 test interface for MCP servers</p>

<Card class="mb-6">
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
		<Input placeholder="Server name" bind:value={serverName} />
		<Input placeholder="Tool name (for tools/call)" bind:value={toolName} />
		<select class="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100" bind:value={method}>
			<option value="initialize">initialize</option>
			<option value="tools/list">tools/list</option>
			<option value="tools/call">tools/call</option>
		</select>
	</div>
	<label class="text-xs text-zinc-500 block mb-1">Params (JSON)</label>
	<textarea
		class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-3"
		rows={4}
		bind:value={params}
	></textarea>
	<Button onclick={call}>Send</Button>
</Card>

{#if result}
	<Card>
		<h2 class="text-sm font-semibold mb-2">Response</h2>
		<pre class="text-xs text-zinc-300 overflow-auto max-h-96 whitespace-pre-wrap">{result}</pre>
	</Card>
{/if}