<script lang="ts">
	import Card from '$lib/components/ui/card.svelte';
	import Button from '$lib/components/ui/button.svelte';
	import Select from '$lib/components/ui/select.svelte';
	import Input from '$lib/components/ui/input.svelte';
	import { getJSON, chatCompletions } from '$lib/api';
	import { panelKey, showToast } from '$lib/stores';
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';

	let models = $state<any[]>([]);
	let selectedModel = $state('');
	let messages = $state([{ role: 'user', content: '' }]);
	let response = $state('');
	let busy = $state(false);
	let temperature = $state('0.7');

	onMount(async () => {
		try {
			const data = await getJSON<any>('/v1/models?limit=200&offset=0');
			models = data.items || [];
			if (models.length) selectedModel = models[0].user_model_id;
		} catch (e: any) {
			showToast(e.message, 'error');
		}
	});

	function addMessage() {
		messages = [...messages, { role: 'user', content: '' }];
	}

	function updateMsg(idx: number, field: string, val: string) {
		const msgs = [...messages];
		(msgs[idx] as any)[field] = val;
		messages = msgs;
	}

	async function send() {
		if (!get(panelKey)) {
			showToast('Login first', 'error');
			return;
		}
		busy = true;
		response = '';
		try {
			const r = await chatCompletions({
				model: selectedModel,
				messages: messages.filter((m) => m.content.trim()),
				temperature: parseFloat(temperature),
				stream: false
			});
			response = JSON.stringify(r, null, 2);
		} catch (e: any) {
			response = `Error: ${e.message}`;
		} finally {
			busy = false;
		}
	}
</script>

<h1 class="text-2xl font-bold mb-6">Playground</h1>

<Card class="mb-6">
	<div class="flex flex-col sm:flex-row gap-3 mb-4 items-end">
		<div class="flex-1 w-full">
			<label class="text-xs text-zinc-500 block mb-1">Model</label>
			<Select bind:value={selectedModel}>
				{#each models as m}
					<option value={m.user_model_id}>{m.user_model_id} ({m.provider?.name})</option>
				{/each}
			</Select>
		</div>
		<div class="w-full sm:w-24">
			<label class="text-xs text-zinc-500 block mb-1">Temp</label>
			<Input type="number" bind:value={temperature} min="0" max="2" step="0.1" />
		</div>
	</div>

	{#each messages as msg, i}
		<div class="mb-3">
			<select
				class="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 mb-1"
				value={msg.role}
				onchange={(e) => updateMsg(i, 'role', (e.target as HTMLSelectElement).value)}
			>
				<option value="system">system</option>
				<option value="user">user</option>
				<option value="assistant">assistant</option>
			</select>
			<textarea
				class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
				rows={3}
				value={msg.content}
				oninput={(e) => updateMsg(i, 'content', (e.target as HTMLTextAreaElement).value)}
			></textarea>
		</div>
	{/each}

	<div class="flex flex-col sm:flex-row gap-3">
		<Button onclick={addMessage}>+ Message</Button>
		<Button onclick={send} disabled={busy || !selectedModel}>{busy ? 'Sending…' : 'Send'}</Button>
	</div>
</Card>

{#if response}
	<Card>
		<h2 class="text-sm font-semibold mb-2">Response</h2>
		<pre class="text-xs text-zinc-300 overflow-auto max-h-96 whitespace-pre-wrap">{response}</pre>
	</Card>
{/if}